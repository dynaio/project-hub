"""Review pipeline: gather context, expose the prompt, run, parse, write."""
import json, re
from pathlib import Path

from .client import AIClient, AIError
from .models import build_chain, describe
from .privacy import Permission, scrub, scrub_sensitive_refs
from .prompts import REVIEW_SYSTEM, review_user_prompt
from .tokens import estimate_tokens
from .profile import compose_system_prompt


SKIP_DIRS = {"node_modules",".git","venv",".venv","env","__pycache__","build",
             "dist","target",".idea",".vscode","site-packages","vendor","obj",
             ".dart_tool",".next",".cache",".gradle","out"}

DEFAULT_FILES = ["README.md","README.rst","README","readme.md",
                 "pyproject.toml","package.json","Cargo.toml","go.mod",
                 "requirements.txt","Makefile","Dockerfile","docker-compose.yml",
                 ".gitignore"]


def walk_tree(root: Path, perm, project_id, max_entries=800):
    lines = []
    def walk(p: Path, depth: int, prefix: str):
        if depth > 5 or len(lines) > max_entries: return
        try:
            entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except (OSError, PermissionError):
            return
        for e in entries:
            if e.name.startswith(".") and e.name not in (".gitignore",".env.example"):
                continue
            if e.is_dir() and e.name in SKIP_DIRS: continue
            rel = e.relative_to(root).as_posix()
            mode = perm.file_mode(project_id, rel)
            if e.is_dir():
                lines.append(f"{prefix}{e.name}/"); walk(e, depth+1, prefix+"  ")
            else:
                if mode == "hidden":
                    lines.append(f"{prefix}[hidden]")
                else:
                    try: size = e.stat().st_size
                    except OSError: size = 0
                    lines.append(f"{prefix}{e.name}  ({size}B)")
    walk(root, 0, "")
    return "\n".join(lines[:max_entries])


def gather_files(root: Path, perm, project_id, paths=None, max_kb=256, db=None):
    out, used = [], 0
    candidates = [Path(p) for p in paths] if paths else \
                 [root / n for n in DEFAULT_FILES if (root / n).is_file()]
    for f in candidates:
        try: rel = f.relative_to(root).as_posix()
        except ValueError: continue
        if not perm.can_read_file(project_id, rel): continue
        try: text = f.read_text(errors="replace")
        except (OSError, UnicodeError): continue
        text = scrub(text)
        if db is not None:
            text = scrub_sensitive_refs(text, project_id, db)
        kb = len(text) / 1024
        if used + kb > max_kb: break
        out.append((rel, text)); used += kb
    return out


def build_payload(db, settings, project_id, send_mode="metadata", files=None):
    perm = Permission(db, settings)
    p = db.get(project_id)
    if not p or not perm.project_visible(project_id):
        raise ValueError("project not visible to AI")
    root = Path(p["path"])
    tree_text = ""
    files_text = ""
    if send_mode in ("tree", "tree+files") and root.is_dir():
        tree_text = walk_tree(root, perm, project_id)
    if send_mode == "tree+files":
        picked = gather_files(root, perm, project_id, paths=files,
                              max_kb=settings.get("ai_max_payload_kb", 256),
                              db=db)
        blocks = []
        for rel, txt in picked:
            blocks.append(f"--- FILE: {rel} ---\n{txt}\n--- END ---")
        files_text = "\n\n".join(blocks)
    return {
        "project": {
            "id": p["id"], "name": p["name"], "path": p["path"],
            "category": p.get("category") or "", "status": p.get("status"),
            "tags": p.get("tags") or "",
            "description": scrub(p.get("description") or ""),
            "remarks": scrub(p.get("remarks") or ""),
        },
        "tree": tree_text,
        "files_text": files_text,
        "send_mode": send_mode,
    }


def build_review_prompt(db, settings, project_id, send_mode="metadata", files=None):
    """Return (system_prompt, user_prompt, payload_dict).

    The system prompt is the base review prompt PLUS the owner's profile and
    standing instructions, so the reviewer knows who it is helping.
    """
    payload = build_payload(db, settings, project_id, send_mode, files)
    p = payload["project"]
    user_msg = review_user_prompt(p, payload["tree"], payload["files_text"],
                                  send_mode)
    system_prompt = compose_system_prompt(REVIEW_SYSTEM, settings)
    return system_prompt, user_msg, payload


def estimate_review_tokens(user_prompt, system_prompt=REVIEW_SYSTEM):
    return estimate_tokens(system_prompt) + estimate_tokens(user_prompt)


def run_review(db, settings, project_id, model_override=None,
               send_mode="metadata", files=None, user_prompt_override=None,
               system_prompt_override=None):
    """Run a review. Returns dict with parsed JSON + _meta."""
    if system_prompt_override:
        system_prompt = system_prompt_override
    else:
        system_prompt = compose_system_prompt(REVIEW_SYSTEM, settings)
    if user_prompt_override:
        user_prompt = user_prompt_override
    else:
        _, user_prompt, _ = build_review_prompt(db, settings, project_id,
                                                send_mode, files)

    api_key = settings.api_key()
    chain = build_chain(api_key, settings.trust_list(),
                        task="project_review", override=model_override)
    if not chain:
        raise RuntimeError("no suitable model")

    last_err = None
    for model_id in chain:
        info = describe(model_id)
        ctx = info.get("context_length") or 128_000

        # fit
        prompt_est = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)
        if prompt_est >= ctx - 512:
            last_err = AIError(
                f"{model_id}: prompt ~{prompt_est} tok > context {ctx}",
                kind="context")
            continue

        provider = settings.get("ai_provider", "openrouter")
        client = AIClient(api_key, provider,
                          custom_base=settings.base_url(provider))
        user_cap = int(settings.get("ai_max_output_tokens", 1024))
        reserve = max(512, ctx - prompt_est - 512)
        max_out = min(user_cap, reserve)
        try:
            resp = client.chat(
                model_id,
                [{"role": "system", "content": system_prompt},
                 {"role": "user",   "content": user_prompt}],
                tools=None, temperature=0.2,
                max_tokens=max_out,
                timeout=240, context_length=ctx)
        except AIError as e:
            last_err = e
            # only auth is terminal; every other error means "try next model"
            if e.kind == "auth":
                raise
            continue

        text = (resp["message"].get("content") or "").strip()
        data = _parse_json(text)
        if data is None:
            last_err = AIError("model did not return JSON", kind="other")
            continue
        data["_meta"] = {
            "model": model_id,
            "usage": resp["usage"],
            "prompt_tokens_estimate": prompt_est,
            "context_length": ctx,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        }
        return data
    raise last_err or RuntimeError("review failed")


def _parse_json(text):
    if not text: return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if not candidate:
        first = text.find("{"); last = text.rfind("}")
        if first != -1 and last > first:
            candidate = text[first:last+1]
    if not candidate: return None
    try: return json.loads(candidate)
    except json.JSONDecodeError: return None


def write_readme(project_path: Path, markdown: str) -> Path:
    target = project_path / "AI_README.md"
    target.write_text(markdown)
    return target
