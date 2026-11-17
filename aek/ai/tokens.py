"""Token estimation and history fitting.

We don't have a real tokenizer for every model, so we approximate:
  * English text:    ~4 chars  = 1 token
  * Code:            ~3 chars  = 1 token
  * CJK / dense:     ~1.5 chars = 1 token

We take the worst case (1.5) and add a 15% safety buffer.
"""
import json


def estimate_tokens(text) -> int:
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    # worst-case ratio + 15% buffer
    return int(len(text) / 1.5 * 1.15) + 1


def estimate_messages_tokens(messages) -> int:
    if not messages:
        return 0
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            c = " ".join(
                x.get("text", "") if isinstance(x, dict) else str(x) for x in c
            )
        total += estimate_tokens(c or "")
        for tc in (m.get("tool_calls") or []):
            total += estimate_tokens(json.dumps(tc))
    # per-message envelope overhead (OpenAI-style)
    total += 4 * len(messages)
    return total


def _valid_tool_order(messages) -> bool:
    """A 'tool' message must follow an assistant message that declared its id."""
    open_ids = set()
    for m in messages:
        role = m.get("role")
        if role == "assistant":
            open_ids = {tc.get("id") for tc in (m.get("tool_calls") or [])
                        if tc.get("id")}
        elif role == "tool":
            tid = m.get("tool_call_id")
            if tid and tid not in open_ids:
                return False
        else:
            open_ids = set()
    return True


def fit_messages(messages, max_input_tokens, max_tool_chars=8000):
    """Return a trimmed copy that fits the budget.

    Strategy:
      1. Truncate big tool results in place.
      2. If still over, drop the oldest middle messages while preserving
         tool-call ordering and always keeping the system message and the
         last user message.
      3. If STILL over (single giant user prompt), truncate the last user
         message content.
    """
    if not messages:
        return messages

    # --- step 1: cap tool result size
    out = []
    for m in messages:
        m2 = dict(m)
        if m2.get("role") == "tool":
            c = str(m2.get("content") or "")
            if len(c) > max_tool_chars:
                m2["content"] = (c[:max_tool_chars]
                                 + "\n\n[...truncated to fit context...]")
        out.append(m2)

    if estimate_messages_tokens(out) <= max_input_tokens:
        return out

    # --- step 2: drop middle
    sys_msg = out[0] if out and out[0].get("role") == "system" else None
    last_user = None
    for m in reversed(out):
        if m.get("role") == "user":
            last_user = m
            break

    head = [sys_msg] if sys_msg else []
    tail = [last_user] if last_user else []
    middle = [m for m in out if m is not sys_msg and m is not last_user]

    while middle and estimate_messages_tokens(head + middle + tail) > max_input_tokens:
        middle.pop(0)

    # drop leading tool messages that lost their parent assistant
    while middle and middle[0].get("role") == "tool":
        middle.pop(0)

    candidate = head + middle + tail
    if estimate_messages_tokens(candidate) <= max_input_tokens:
        return candidate

    # --- step 3: hard-truncate the last user message
    if tail and tail[0] is not None:
        last = dict(tail[0])
        content = str(last.get("content") or "")
        # how many tokens do we need to cut?
        over = estimate_messages_tokens(head + [last]) - max_input_tokens
        cut_chars = max(200, int(over * 1.5 * 1.2))
        if len(content) > cut_chars:
            last["content"] = ("[...truncated to fit context window...]\n\n"
                               + content[-max(200, len(content) - cut_chars):])
        else:
            last["content"] = "[prompt too large — most content removed]"
        tail = [last]

    return head + middle + tail
