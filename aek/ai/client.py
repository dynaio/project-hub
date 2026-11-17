"""OpenRouter / Naraya / Pollinations / Ollama / Custom client.

Uses the official openai Python SDK. Every supported provider is
OpenAI-compatible — only the base_url changes.

  OpenRouter     https://openrouter.ai/api/v1
  Naraya         https://router.bynara.id/v1
  Pollinations   https://gen.pollinations.ai/v1
  Ollama         http://127.0.0.1:11434/v1
  Custom         whatever the user configures
"""
import re
import time
import requests

try:
    from openai import OpenAI, OpenAIError
    HAVE_OPENAI = True
except ImportError:
    HAVE_OPENAI = False
    OpenAI = None
    OpenAIError = Exception

from ..config import (OPENROUTER_BASE, OLLAMA_BASE,
                      NARAYA_BASE, POLLINATIONS_BASE)
from .tokens import estimate_messages_tokens


class AIError(Exception):
    def __init__(self, msg, status=None, kind=None):
        super().__init__(msg)
        self.status = status
        self.kind = kind
        # kind values:
        #   auth             — 401/403, wrong key
        #   credit           — 402, account out of money
        #   credit_exhausted — 402, "can only afford < 512"
        #   rate             — 429, or 402 "in-flight"
        #   context          — prompt > model context window
        #   network          — timeout or connection failure
        #   config           — missing package or missing key
        #   other            — anything else


def _parse_afford(msg):
    """OpenRouter: 'you can only afford 1655'. Pull the number out."""
    if not msg:
        return 0
    m = re.search(r"can only afford\s+(\d+)", msg)
    return int(m.group(1)) if m else 0


def _classify(status, msg):
    low = (msg or "").lower()
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "rate"
    if status == 402:
        afford = _parse_afford(msg)
        if afford and afford < 512:
            return "credit_exhausted"
        return "credit"
    if "context" in low and ("length" in low or "window" in low or "token" in low):
        return "context"
    return "other"


class AIClient:
    def __init__(self, api_key, provider="openrouter", custom_base=""):
        self.api_key = api_key or ""
        self.provider = provider
        self.custom_base = custom_base or ""
        self._sdk = None

    def _base(self):
        base = self.custom_base or ""
        if base:
            return base.rstrip("/")
        if self.provider == "ollama":
            return OLLAMA_BASE
        if self.provider == "naraya":
            return NARAYA_BASE
        if self.provider == "pollinations":
            return POLLINATIONS_BASE
        return OPENROUTER_BASE

    def _sdk_client(self):
        if self._sdk is not None:
            return self._sdk
        if not HAVE_OPENAI:
            raise AIError(
                "The 'openai' package is required for chat.\n"
                "    pip install 'openai>=1.50'\n"
                "or re-run install.sh.",
                kind="config")
        headers = {}
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/dynaio/project-hub"
            headers["X-Title"] = "aek"
        self._sdk = OpenAI(
            api_key=self.api_key or "sk-no-key",
            base_url=self._base(),
            timeout=120.0,
            max_retries=1,
            default_headers=headers or None,
        )
        return self._sdk

    # ------------------------------------------------------------------
    def chat(self, model, messages, tools=None, tool_choice="auto",
             temperature=0.3, max_tokens=None, timeout=180,
             context_length=None):
        if context_length is None:
            from .models import describe
            context_length = describe(model).get("context_length") or 128_000

        prompt_tokens = estimate_messages_tokens(messages)

        if max_tokens is None:
            reserve = min(4096, max(512, context_length // 16))
            avail = context_length - prompt_tokens - 256
            if avail < 256:
                raise AIError(
                    f"Prompt is ~{prompt_tokens} tokens but model context is "
                    f"{context_length}. Even after trimming there is no room "
                    f"for a reply.",
                    kind="context")
            max_tokens = min(reserve, avail)

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        client = self._sdk_client()

        # Manual retry only for the "in-flight" 402 (soft rate limit).
        # Everything else is handled by the SDK's max_retries or raises.
        resp = None
        last_exc = None
        for attempt in range(4):
            try:
                resp = client.chat.completions.create(**kwargs)
                break
            except OpenAIError as e:
                last_exc = e
                cls = type(e).__name__
                msg = str(e)
                status = getattr(e, "status_code", None)
                low = msg.lower()

                if cls in ("APITimeoutError", "APIConnectionError"):
                    raise AIError(f"network: {msg}", kind="network") from e

                if (status == 402
                        and ("in-flight" in low or "settle" in low)
                        and attempt < 3):
                    time.sleep(2.0 * (attempt + 1))
                    continue

                kind = _classify(status, msg)
                raise AIError(msg, status=status, kind=kind) from e

        if resp is None:
            status = getattr(last_exc, "status_code", None) if last_exc else None
            msg = str(last_exc) if last_exc else "no response"
            raise AIError(msg, status=status,
                          kind=_classify(status, msg)) from last_exc

        # ---- normalize SDK response → dict shape aek expects ----
        choice = resp.choices[0]
        msg_obj = choice.message
        content = msg_obj.content or ""

        tool_calls = None
        if getattr(msg_obj, "tool_calls", None):
            tool_calls = []
            for tc in msg_obj.tool_calls:
                fn = getattr(tc, "function", None)
                tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": fn.name if fn else "",
                        "arguments": fn.arguments if fn else "{}",
                    },
                })

        out_message = {"role": "assistant", "content": content}
        if tool_calls:
            out_message["tool_calls"] = tool_calls

        usage_obj = resp.usage
        usage = {
            "in": getattr(usage_obj, "prompt_tokens", 0) or 0,
            "out": getattr(usage_obj, "completion_tokens", 0) or 0,
        }

        try:
            raw = resp.model_dump()
        except Exception:
            raw = {}

        return {
            "message": out_message,
            "finish_reason": choice.finish_reason,
            "usage": usage,
            "prompt_tokens_estimate": prompt_tokens,
            "max_tokens": max_tokens,
            "raw": raw,
        }

    # ------------------------------------------------------------------
    def check_key(self):
        """Balance check via OpenRouter's /key. Other providers report
        neutral ('unlimited') so the agent doesn't try to compute a
        low-credit fallback on them."""
        if self.provider in ("ollama", "naraya", "pollinations", "custom"):
            return {"provider": self.provider, "unlimited": True,
                    "reason": "no per-request billing on this provider"}
        try:
            r = requests.get(f"{self._base()}/key",
                             headers={"Authorization": f"Bearer {self.api_key}"},
                             timeout=15)
            if r.status_code != 200:
                return {}
            d = (r.json() or {}).get("data") or {}
            return {
                "label": d.get("label"),
                "limit": d.get("limit"),
                "limit_remaining": d.get("limit_remaining"),
                "usage": d.get("usage"),
                "is_free_tier": d.get("is_free_tier"),
                "free_daily_used": (d.get("free_model_daily_requests") or {}).get("used"),
                "free_daily_max": (d.get("free_model_daily_requests") or {}).get("limit"),
                "free_daily_left": (d.get("free_model_daily_requests") or {}).get("remaining"),
            }
        except Exception:
            return {}

    def models(self):
        """Legacy /models fetch. The app uses fetch_models() in
        models.py, which handles caching and provider rotation."""
        try:
            r = requests.get(f"{self._base()}/models",
                             headers={"Authorization": f"Bearer {self.api_key}"},
                             timeout=20)
            if r.status_code == 200:
                return r.json().get("data") or []
        except Exception:
            pass
        return []
