"""Agent loop, running in a QThread, with token budgeting."""
import json, threading
from PyQt6.QtCore import QThread, pyqtSignal

from .client import AIClient, AIError
from .models import build_chain, describe
from .privacy import Permission
from .tools import TOOLS, ToolRunner
from .tokens import fit_messages, estimate_messages_tokens
from .profile import compose_system_prompt
from .summary import should_summarize, summarize_messages
from . import audit


class AgentWorker(QThread):
    assistant_msg   = pyqtSignal(str)
    tool_call       = pyqtSignal(dict)
    tool_result     = pyqtSignal(dict)
    done            = pyqtSignal(dict)
    error           = pyqtSignal(str)
    permission_ask  = pyqtSignal(dict)
    tokens_update   = pyqtSignal(dict)     # {in, out, pct}

    def __init__(self, db, settings, history, project_id=None,
                 system_prompt="", task_profile="agentic",
                 model_override=None, max_steps=12, chat_id=None,
                 parent=None):
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.history = list(history)
        self.project_id = project_id
        self.system_prompt = system_prompt
        self.task_profile = task_profile
        self.model_override = model_override
        self.max_steps = max_steps
        self.chat_id = chat_id

        self._perm_event = threading.Event()
        self._perm_result = False
        self._stop = False

    # UI thread
    def answer_permission(self, ok):
        self._perm_result = bool(ok)
        self._perm_event.set()

    def stop(self):
        self._stop = True
        self._perm_event.set()

    def _approver(self, tool_name, args):
        self._perm_event.clear()
        self._perm_result = False
        self.permission_ask.emit({"tool": tool_name, "args": args})
        self._perm_event.wait(timeout=180)
        return self._perm_result

    # worker thread
    def run(self):
        api_key = self.settings.api_key()
        if not api_key and self.settings.get("ai_provider") == "openrouter":
            self.error.emit("No OpenRouter API key configured."); return

        try:
            chain = build_chain(api_key, self.settings.trust_list(),
                                task=self.task_profile,
                                override=self.model_override)
        except Exception as e:
            self.error.emit(f"model selection failed: {e}"); return
        if not chain:
            self.error.emit("No suitable model found."); return

        perm = Permission(self.db, self.settings)
        runner = ToolRunner(self.db, self.settings, perm, model_id=chain[0])
        runner.approver = self._approver

        system_prompt = compose_system_prompt(self.system_prompt, self.settings)
        base_messages = [{"role": "system", "content": system_prompt}]
        base_messages.extend(self.history)

        tokens_in = tokens_out = 0
        used_model = chain[0]

        for step in range(self.max_steps):
            if self._stop: return

            # ---- pick a model that fits
            response = None
            last_err = None
            for model_id in chain:
                info = describe(model_id)
                ctx = info.get("context_length") or 128_000

                fitted = fit_messages(base_messages, int(ctx * 0.85))
                est = estimate_messages_tokens(fitted)

                # If even after trimming we can't fit, try the next model
                if est > ctx - 512:
                    last_err = AIError(
                        f"{model_id} cannot fit prompt ({est} > {ctx})",
                        kind="context")
                    continue

                provider = self.settings.get("ai_provider", "openrouter")
                client = AIClient(api_key, provider,
                                  custom_base=self.settings.base_url(provider))
                # reserve for output, respect user cap
                user_cap = int(self.settings.get("ai_max_output_tokens", 1024))
                reserve = max(512, ctx - est - 512)
                max_out = min(user_cap, reserve)
                try:
                    response = client.chat(
                        model_id, fitted, tools=TOOLS, temperature=0.3,
                        context_length=ctx, max_tokens=max_out,
                        timeout=30)
                    used_model = model_id
                    self.tokens_update.emit({
                        "in": tokens_in + response["usage"]["in"],
                        "out": tokens_out + response["usage"]["out"],
                        "est": est,
                        "ctx": ctx,
                        "model": model_id,
                        "pct": round(100 * (est + response["max_tokens"]) / ctx),
                    })
                    break
                except AIError as e:
                    last_err = e
                    if e.kind == "auth":
                        self.error.emit(
                            f"{model_id}: {e}\n\n"
                            "Check your API key in Settings → AI.")
                        return

                    reason = str(e)
                    if len(reason) > 100:
                        reason = reason[:97] + "…"
                    self.tool_result.emit({
                        "name": "(fallback)",
                        "ok": False,
                        "summary": f"{model_id} failed: {reason} — trying next model",
                    })

                    # If this looks like a credit issue, force the rest of
                    # the chain to be free-only.
                    if e.kind in ("credit", "credit_exhausted"):
                        try:
                            from .models import free_chain, _BALANCE_CACHE
                            _BALANCE_CACHE["at"] = 0  # invalidate
                            _BALANCE_CACHE["data"] = {"limit_remaining": 0,
                                                      "is_free_tier": True}
                            # replace chain tail with free models
                            remaining = chain[chain.index(model_id) + 1:]
                            free = [m for m in free_chain(8)
                                    if m not in chain[:chain.index(model_id) + 1]]
                            chain = chain[:chain.index(model_id) + 1] + free
                            self.tool_result.emit({
                                "name": "(fallback)",
                                "ok": False,
                                "summary": "credit issue → switching to free models",
                            })
                        except Exception:
                            pass
                    continue

            if response is None:
                self.error.emit(f"all models failed: {last_err}"); return

            tokens_in += response["usage"]["in"]
            tokens_out += response["usage"]["out"]
            msg = response["message"]

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                text = msg.get("content") or ""
                self.assistant_msg.emit(text)
                # persist final assistant turn
                if self.chat_id:
                    try:
                        self.db.chat_add_message(self.chat_id, "assistant", text)
                    except Exception:
                        pass
                    self._maybe_summarize(base_messages, used_model)
                self._log(used_model, tokens_in, tokens_out, base_messages)
                self.done.emit({"tokens_in": tokens_in, "tokens_out": tokens_out,
                                "model": used_model, "steps": step + 1})
                return

            base_messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                if self._stop: return
                name = tc.get("function", {}).get("name", "")
                raw = tc.get("function", {}).get("arguments") or "{}"
                try:
                    args = json.loads(raw)
                except json.JSONDecodeError:
                    args = {}
                self.tool_call.emit({"name": name, "args": args})
                result = runner.call(name, args)
                summary = self._summarize(name, result)
                self.tool_result.emit({"name": name, "ok": "error" not in result,
                                       "summary": summary})

                payload = json.dumps(result)
                if len(payload) > 40_000:
                    payload = payload[:40_000] + '"}[truncated]"'
                base_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "name": name,
                    "content": payload,
                })
            if self._stop: return

        self.error.emit("agent reached max steps without final answer")

    def _summarize(self, name, result):
        if "error" in result:
            return f"error: {result['error']}"
        if name == "read_file":      return f"{result.get('bytes',0)} bytes"
        if name == "list_dir":       return f"{len(result.get('entries',[]))} entries"
        if name == "search_code":    return f"{result.get('count',0)} hits"
        if name == "list_projects":  return f"{result.get('count',0)} projects"
        if name == "get_git_log":    return f"{len(result.get('commits',[]))} commits"
        return "ok"

    def _maybe_summarize(self, messages, model_id):

        """If the running context exceeds 60% of the model's

        window, summarize old turns and store the summary on

        the chat row."""

        if not self.chat_id:

            return

        info = describe(model_id)

        ctx = info.get("context_length") or 128_000

        conv = [m for m in messages if m.get("role") != "system"]

        if not should_summarize(conv, ctx, threshold=0.6):

            return

        rows = self.db.chat_messages(self.chat_id, after_id=0)

        if len(rows) < 20:

            return

        cut = int(len(rows) * 0.6)

        to_summarize = rows[:cut]

        try:

            summarize_messages(self.db, self.settings, self.chat_id,

                               to_summarize, model_override=None)

        except Exception:

            pass


    def _log(self, model, tin, tout, messages):
        try:
            preview = ""
            for m in messages:
                if m["role"] == "user":
                    preview = (m.get("content") or "")[:300]; break
            self.db.ai_log(project_id=self.project_id, kind=self.task_profile,
                           model=model, prompt_preview=preview,
                           tokens_in=tin, tokens_out=tout, cost=0)
        except Exception:
            pass
