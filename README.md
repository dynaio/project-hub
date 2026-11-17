# aek

A native PyQt6 desktop app for organizing, understanding, and working with
every project on your machine — with a local-first AI agent that reads what
you allow it to read.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.5+-green)
![Platform](https://img.shields.io/badge/platform-Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## The problem

Over years of research and side projects, ~/Code fills with folders. Some are
innovative. Some are abandoned mid-flight. Resuming one means re-reading it
folder by folder.

`aek` gives every project a card with a cover, a description, notes, a
category, a status, and — if you allow it — an AI that can read the code and
talk to you about it.

## What it does

### Personal project hub
- **Card grid** — cover image, name, path, description, tags, category stripe,
  status pill, favorite star, missing-folder warning
- **Details view** — click any card for a full view with all metadata,
  custom fields, and one-click actions
- **Categories and groups** — free-text with `/` nesting (`AI/Vision`),
  managed from a dedicated dialog
- **Configurable statuses** — active / idea / paused / done / archived, plus
  any you add
- **Custom fields** — text, multiline, choice, or URL. Define them once, fill
  them per project
- **Zoom** — four card sizes from toolbar or `Ctrl+=` / `Ctrl+-`
- **Search** — free text plus operators: `cat:web`, `tag:ai`, `status:paused`
- **Recent bar** — last 8 opened projects, always one click away
- **Sort modes** — custom drag order, name, recent, added, status
- **Grouping** — flat, by category, or by status
- **Snapshot export / import** — full JSON including cover images
- **Statistics** — counts by status and category, with disk usage
- **System tray** — quick access to recent projects

### AI agent (opt-in per project)
- **Review any project** — click AI review, edit the prompt, get a structured
  response with suggested description, remarks, tags, and a full `AI_README.md`
- **Chat with your library** — global or per-project; the agent reads through
  tools you control
- **Persistent chats** — resumes across restarts, with rolling summaries
- **Agentic tools** — list projects, read files, search code, read git log,
  update metadata, create reminders
- **Privilege system** — every tool is toggleable in Settings → Privileges
- **Sensitivity model** — per-project AI access flag plus a file picker that
  marks folders or files as invisible
- **Prompt files** — `user_profile.md` (you + AI) and `system_prompt.md`
  (you only), both editable in-app or in your system editor
- **Fallback chain** — tries models in your trust list, prefers free models
  when asked, handles 402 credit errors gracefully
- **Audit trail** — every read the agent makes is logged

### Notifications
- **Reminders** — per project, with due date and advance warning
- **In-app toasts** plus optional system-tray notifications

## Install

```bash
git clone https://github.com/dynaio/project-hub.git
cd project-hub
./install.sh
aek
