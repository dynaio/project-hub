"""Minimal markdown → HTML for the chat panel.

Handles:
- Fenced code blocks: ```lang ... ```
- Inline code: `code`
- Bold (**text**), italic (*text*)
- Links: [text](url)
- Headers: # ## ###
- Bullet lists: - or *
- Blockquotes: >
- Newlines inside paragraphs

Everything else is HTML-escaped and shown verbatim. Output is a subset of
HTML 4 that Qt's QTextBrowser supports, with inline styles for code.
"""

import html
import re


_CODE_RE = re.compile(r'```([\w+-]*)\r?\n?(.*?)```', re.DOTALL)

_INLINE_CODE_STYLE = (
    "background:#eef1f6;padding:1px 5px;border-radius:3px;"
    "font-family:'Ubuntu Sans Mono','DejaVu Sans Mono',monospace;"
    "font-size:12px;"
)
_CODE_BLOCK_STYLE = (
    "background:#eef1f6;color:#1f2330;padding:10px 12px;"
    "border-radius:6px;font-family:'Ubuntu Sans Mono','DejaVu Sans Mono',"
    "monospace;font-size:12px;white-space:pre-wrap;margin:8px 0;"
)


def render(text: str) -> str:
    """Return HTML for QTextBrowser."""
    if not text:
        return ""

    parts = []
    idx = 0
    for m in _CODE_RE.finditer(text):
        parts.append(("text", text[idx:m.start()]))
        parts.append(("code", (m.group(1) or "", m.group(2))))
        idx = m.end()
    parts.append(("text", text[idx:]))

    out = []
    for kind, payload in parts:
        if kind == "code":
            lang, body = payload
            body_html = html.escape(body.rstrip("\n"))
            label = f'<div style="color:#8a92a3;font-size:10px;margin-bottom:2px;">{html.escape(lang)}</div>' \
                    if lang else ""
            out.append(
                f'{label}'
                f'<pre style="{_CODE_BLOCK_STYLE}">{body_html}</pre>'
            )
        else:
            out.append(_render_text(payload))
    return "".join(out)


def _render_text(text: str) -> str:
    if not text:
        return ""

    t = html.escape(text)

    # inline code
    t = re.sub(r'`([^`\n]+)`',
               rf'<code style="{_INLINE_CODE_STYLE}">\1</code>',
               t)

    # bold before italic
    t = re.sub(r'\*\*([^*\n]+)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', t)

    # links
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', t)

    # headers (converted to bold lines, since Qt handles them awkwardly)
    t = re.sub(r'^### (.+)$', r'<b>\1</b>', t, flags=re.MULTILINE)
    t = re.sub(r'^## (.+)$',
               r'<b style="font-size:14px;">\1</b>', t, flags=re.MULTILINE)
    t = re.sub(r'^# (.+)$',
               r'<b style="font-size:15px;">\1</b>', t, flags=re.MULTILINE)

    # list items
    t = re.sub(r'^[-*] (.+)$', r'&nbsp;&nbsp;• \1', t, flags=re.MULTILINE)

    # blockquotes
    t = re.sub(r'^&gt; (.+)$',
               r'<i style="color:#6b7280;">\1</i>', t, flags=re.MULTILINE)

    # newlines → <br>
    t = t.replace("\n", "<br>")
    return t
