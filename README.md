# aek

A native desktop app for keeping track of every project on your machine.
Stop re-discovering your own folders every time you try to resume something
you started months ago.

Built with Python and PyQt6. Runs on Linux. No web layer, no browser, no cloud.

---

## Features

- **Card grid** — every project is a card with a cover image, name, folder path,
  description, tags, category stripe and a status pill.
- **Click to open** — click a card to open its folder. Buttons for a terminal
  inside the project and for opening it in your code editor.
- **Categories and groups** — free-text category per project. Use `/` to nest
  (`AI/Vision`). The sidebar shows a tree. A separate "Groups" dialog lets you
  create, rename, recolor and delete groups at any time; renaming a group
  cascades to every project that uses it.
- **Grouping view** — group cards by category or status, or keep them flat.
- **Sort modes** — custom (drag order) · name · recently opened · recently added ·
  status.
- **Recent bar** — a horizontal strip of the last 8 opened projects, always
  visible above the grid.
- **Sidebar filters** — All · Favorites · Recently opened · Uncategorized ·
  every category (nested).
- **Search** — free text plus operators: `cat:web`, `tag:ai`, `status:paused`.
- **Statistics dialog** — project counts by status and category, with on-demand
  disk usage per category.
- **Export / import** — full JSON snapshot including cover images (base64).
  Merge or replace.
- **System tray** — right-click for quick access to recent projects, rescan,
  show and quit. The app keeps running in the tray when you close the window.
- **Theme toggle** — light and dark themes, applied with a smooth crossfade and
  persisted across restarts.
- **Animations** — staggered card fade-in, animated toasts, smooth theme
  transitions, hover states.
- **Cover images** — pick one manually, or let aek auto-detect `cover.png`,
  `screenshot.png`, `preview.jpg`, `logo.png` inside a project.
- **Missing-folder badge** — a card whose path no longer exists shows a red
  `MISSING` badge and warns before opening.
- **Remarks** — a free-text “where I left off” field per project, so future-you
  knows what past-you was doing.
- **Everything local** — a single SQLite file plus a covers directory under
  `~/.aek/data/`. No telemetry, no accounts.

Removing a card never touches files on disk.

---

## Install

```bash
git clone https://github.com/<you>/aek.git
cd aek
./install.sh
