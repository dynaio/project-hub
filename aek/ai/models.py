"""Model discovery, ranking, and fallback chain."""
import json, time
from pathlib import Path
from ..config import AI_CACHE, OPENROUTER_BASE


# task profiles
# ---- credit balance cache (checked every 5 min)
_BALANCE_CACHE = {"at": 0.0, "data": {}}
_BALANCE_TTL = 300  # seconds


TASK_PROFILES = {
    # cheap model for interactive chat; avoids credit exhaustion
    "chat_cheap":     {"needs_tools": True,  "min_context": 128_000, "prefer_pro": False},
    "quick_chat":     {"needs_tools": True,  "min_context": 16_000,  "prefer_pro": False},
    "project_review": {"needs_tools": True,  "min_context": 200_000, "prefer_pro": True},
    "full_project":   {"needs_tools": True,  "min_context": 1_000_000,"prefer_pro": True},
    "agentic":        {"needs_tools": True,  "min_context": 128_000, "prefer_pro": True},
    "simple":         {"needs_tools": False, "min_context": 8_000,   "prefer_pro": False},
}


def _load_cache():
    if AI_CACHE.exists():
        try:
            return json.loads(AI_CACHE.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    return {"fetched_at": 0, "models": []}


def _save_cache(d):
    try:
        AI_CACHE.write_text(json.dumps(d))
    except OSError:
        pass


def fetch_models(api_key, force=False):
    """Fetch /models from OpenRouter. Cache for 24h. Never raises."""
    cache = _load_cache()
    age = time.time() - cache.get("fetched_at", 0)
    if not force and age < 86_400 and cache.get("models"):
        return cache["models"]
    try:
        import requests
        r = requests.get(f"{OPENROUTER_BASE}/models",
                         headers={"Authorization": f"Bearer {api_key}"},
                         timeout=20)
        r.raise_for_status()
        raw = r.json().get("data", [])
        models = []
        import math
        for m in raw:
            arch = m.get("architecture") or {}
            pricing = m.get("pricing") or {}
            modalities = arch.get("input_modalities") or []
            try:
                in_price = float(pricing.get("prompt") or 0)
                out_price = float(pricing.get("completion") or 0)
            except (TypeError, ValueError):
                in_price = out_price = 0.0
            # Negative = sentinel for variable-price routers → treat as unknown.
            # NaN/inf = bad data.
            if (not math.isfinite(in_price) or not math.isfinite(out_price)
                    or in_price < 0 or out_price < 0):
                in_price = out_price = -1.0   # marker: "unknown price"
            mid = str(m.get("id", ""))
            models.append({
                "id": mid,
                "name": m.get("name") or mid,
                "context_length": int(m.get("context_length") or 0),
                "input_price": in_price,
                "output_price": out_price,
                "supports_tools": bool(m.get("supported_parameters")
                                       and "tools" in (m.get("supported_parameters") or [])),
                "supports_vision": "image" in modalities,
                "modality": arch.get("modality", "text->text"),
                "pricing_known": in_price >= 0 and out_price >= 0,
                # batch models use the batch endpoint, not /chat/completions
                "is_batch": mid.endswith(":batch") or ":batch" in mid,
            })
        cache = {"fetched_at": time.time(), "models": models}
        _save_cache(cache)
        return models
    except Exception:
        return cache.get("models", [])


def _matches(model, profile):
    # batch-only models can't be called on /chat/completions
    if model.get("is_batch"):
        return False
    if model["context_length"] < profile["min_context"]:
        return False
    if profile.get("needs_tools") and not model["supports_tools"]:
        return False
    return True


def _score(model, profile):
    """Higher is better. Unknown prices don't score better than cheap ones."""
    s = 0.0
    s += min(model["context_length"] / 1_000_000, 4.0)
    if model["supports_tools"]: s += 0.5
    if model["supports_vision"]: s += 0.1
    ip = model.get("input_price", 0) or 0
    op = model.get("output_price", 0) or 0
    if ip < 0 or op < 0:
        # unknown price → small penalty, don't reward
        s -= 0.3
    else:
        price = ip + op
        s -= min(price * 200, 2.0)
    if profile.get("prefer_pro") and any(
        k in model["id"].lower() for k in ("pro", "opus", "sonnet", "gpt-4o", "r1")
    ):
        s += 1.0
    return s


def check_balance(api_key, provider="openrouter", force=False):
    """Return cached balance info. Refreshes at most every 5 min."""
    import time
    now = time.time()
    if (not force
            and _BALANCE_CACHE.get("data")
            and now - _BALANCE_CACHE.get("at", 0) < _BALANCE_TTL):
        return _BALANCE_CACHE["data"]
    from .client import AIClient
    client = AIClient(api_key, provider)
    info = client.check_key()
    _BALANCE_CACHE["at"] = now
    _BALANCE_CACHE["data"] = info
    return info


def account_is_low(api_key, provider="openrouter"):
    """True when the account can't afford paid models — use free only."""
    info = check_balance(api_key, provider)
    if not info:
        return False  # unknown → let the chain try normally
    rem = info.get("limit_remaining")
    if rem is None:
        # no per-key limit, only free tier daily limit matters
        return bool(info.get("is_free_tier"))
    try:
        return float(rem) <= 0.05  # ≤ 5 cents → treat as low
    except (TypeError, ValueError):
        return False


FREE_ROUTER = "openrouter/free"


def free_chain(limit=6):
    """A dedicated chain of free-only entries, best-first.

    Order matters:
      1. openrouter/free   — the official free router (updated by OpenRouter)
      2. openrouter/auto   — the paid router, which falls back to free models
                             when balance is low
      3. Explicit :free models — direct calls, no routing
    """
    return [FREE_ROUTER,
            "openrouter/auto",
            "meta-llama/llama-4-scout",
            "deepseek/deepseek-v4-flash",
            "qwen/qwen3.6-flash",
            "google/gemini-2.5-flash-lite",
            "thinkingmachines/inkling-small:free"][:limit]


def _valid_model_for_provider(model_id, provider):
    """Pollinations uses short aliases (no '/'); the others accept
    vendor/model paths."""
    if not model_id:
        return False
    if provider == "pollinations":
        return "/" not in model_id
    return True


def build_chain(api_key, trust_list, task="quick_chat",
                override=None, limit=8, prefer_free=False,
                provider="openrouter", base_url=""):
    """Return an ordered list of model IDs, primary first."""
    models = fetch_models(api_key, provider=provider,
                          base_url=base_url)
    # filter model IDs that don't match this provider's naming scheme
    if override and _valid_model_for_provider(override, provider):
        ordered = [override]
    else:
        ordered = []

    # clean the trust list too
    _clean_trust = [m for m in (trust_list or [])
                    if _valid_model_for_provider(m, provider)]

    profile = TASK_PROFILES.get(task, TASK_PROFILES["quick_chat"])
    by_id = {m["id"]: m for m in models}

    # ---- tier 1: trust list substrings, in order
    trust_hits = []
    for pat in trust_list or []:
        p = pat.lower()
        for mid, m in by_id.items():
            if p in mid.lower() and _matches(m, profile):
                if mid not in trust_hits:
                    trust_hits.append(mid)
    ordered.extend([m for m in trust_hits if m not in ordered])

    # ---- tier 2: known-price first, then unknown-price
    candidates = [m for m in models if _matches(m, profile) and m["id"] not in ordered]
    known = [m for m in candidates if m.get("pricing_known", True)]
    unknown = [m for m in candidates if not m.get("pricing_known", True)]
    known.sort(key=lambda m: _score(m, profile), reverse=True)
    unknown.sort(key=lambda m: _score(m, profile), reverse=True)
    ordered.extend([m["id"] for m in (known + unknown)[:limit]])

    # ---- tier 3: emergency — biggest context available
    if not ordered and models:
        biggest = max(models, key=lambda m: m["context_length"])
        ordered.append(biggest["id"])

    return ordered[:limit]


def describe(model_id):
    for m in _load_cache().get("models", []):
        if m["id"] == model_id:
            return m
    return {"id": model_id, "name": model_id, "context_length": 0,
            "input_price": 0, "output_price": 0,
            "supports_tools": False, "supports_vision": False}
