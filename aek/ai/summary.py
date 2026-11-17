"""Summarize old chat messages so the context stays bounded."""
from .client import AIClient, AIError
from .models import build_chain, describe
from .tokens import estimate_tokens


SUMMARIZE_SYSTEM = """You compress a chat history into a dense summary.

Rules:
- Preserve: what the user asked, decisions made, facts learned, next steps.
- Drop: pleasantries, repeated explanations, raw tool output (summarize it).
- Never invent facts.
- Return plain text, no markdown headers, no code fences."""


def should_summarize(messages, context_length, threshold=0.6):
    """True when messages exceed `threshold` of the model's context."""
    est = sum(estimate_tokens(m.get("content") or "") for m in messages)
    est += 8 * len(messages)
    return est > context_length * threshold


def summarize_messages(db, settings, chat_id, messages, model_override=None):
    """Summarize messages and store the result on the chat row.
    Returns (summary_text, upto_id) or None on failure."""
    if not messages:
        return None

    # build a single user prompt with the transcript
    lines = []
    for m in messages:
        role = m.get("role", "?")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "tool":
            name = m.get("name") or "tool"
            lines.append(f"[{name} result] {content[:400]}")
        else:
            lines.append(f"[{role}] {content[:800]}")

    transcript = "\n".join(lines)
    chat = db.chat_get(chat_id) or {}
    prev = (chat.get("summary") or "").strip()

    user_prompt = (
        (f"Previous summary (already compressed):\n{prev}\n\n"
         if prev else "")
        + "Transcript to compress:\n"
        + transcript
    )

    api_key = settings.api_key()
    if not api_key and settings.get("ai_provider") == "openrouter":
        return None

    # use a cheap model for summaries
    chain = build_chain(api_key, settings.trust_list(),
                        task="simple", override=model_override)
    if not chain:
        return None

    for model_id in chain[:3]:
        info = describe(model_id)
        ctx = info.get("context_length") or 128_000
        if estimate_tokens(SUMMARIZE_SYSTEM) + estimate_tokens(user_prompt) > ctx - 512:
            continue
        try:
            provider = settings.get("ai_provider", "openrouter")
            client = AIClient(api_key, provider,
                              custom_base=settings.base_url(provider))
            r = client.chat(
                model_id,
                [{"role": "system", "content": SUMMARIZE_SYSTEM},
                 {"role": "user",   "content": user_prompt}],
                tools=None, temperature=0.2,
                max_tokens=min(800, settings.get("ai_max_output_tokens", 1024)),
                timeout=60, context_length=ctx)
            text = (r["message"].get("content") or "").strip()
            if not text:
                continue
            upto = messages[-1].get("id") or 0
            db.chat_update_summary(chat_id, text, upto)
            return text, upto
        except AIError:
            continue
        except Exception:
            continue
    return None
