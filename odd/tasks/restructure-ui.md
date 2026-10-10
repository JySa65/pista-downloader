# Feature: restructure-ui

## Objective
Split the single-file Tkinter app into a testable `core` (no Tkinter) and a `ui` package, restyle it with sv-ttk, add playlist/Mix-aware track selection, and an in-app video preview.

## Problem / Why
`main.py` mixes UI, threading, and yt-dlp in one ~400-line class. Playlist and Mix handling is implicit, and several known bugs exist: tree scrollbar, thumbnail fetch blocking the UI, Stop not aborting the current download, and the logged path not matching the real file.

## Scope
- `youtube_download/core`: models, URL classification (video | playlist | mix), downloader (list tracks, download with progress, cancel).
- `youtube_download/ui`: sv-ttk themed app, track table with check selection, worker thread with queue, preview button.
- Real playlists load all tracks; Mix (`list=RD...`) asks "only this video or Mix (cap N)".
- Per-playlist output folder, `download_archive` to skip already downloaded tracks.
- Preview: separate native window via pywebview subprocess; fallback ffplay; last fallback browser.

## Constraints
Python 3.14, uv, NiceGUI (native window). No hexagonal ports (single adapter). Artifacts in English.

## Delivery strategy
ask-on-risk. Forecast ~600 authored lines.

## Tasks
- [x] T1 core package + tests/test_urls.py (route: delegated writer) — commit 9b827a4, pytest 15 passed, live list_tracks on Mix OK
- [x] T2 NiceGUI desktop UI (native=True) + preview (YouTube iframe + 30s local clip fallback) + main.py entrypoint (route: delegated writer). Decision: Tkinter dropped — cannot render video; NiceGUI native verified on this Mac (iframe + local mp4 both play). playable_in_embed is unreliable (True for a blocked video), so both preview modes are user-triggered. — commit fe6abf9; pytest 17 passed (adds tests/test_preview.py, RED observed first); core imports without nicegui; live preview_clip on VIDEOID0001 → 30 s mp4 with video+audio (ffprobe); launch smoke: process alive after 7 s, page served on :8000 with expected controls, no traceback.
- [x] T3 deps, README, remove old code paths (route: delegated writer) — Tkinter main.py replaced in fe6abf9; unused pillow/requests removed; README added in the docs commit.
- [x] T4 apply Claude Design mockup (route: delegated writer) — commit be8c235. Two tabs (Descargar / Reproductor), design tokens in ui/theme.py (light default + dark), Formato MP3/MP4 + Calidad/Resolución (core format_opts, per-format download archives), local MP3 player (core/library.py), cross-platform helpers (core/system.py: clipboard per OS, default folder, ffmpeg check; windowsfilenames; --browser fallback), window opens maximized. Evidence: pytest 32 passed (RED observed for test_library, test_format_opts, test_system); live MP4 360p download → ffprobe video+audio, per-format archive skip OK; headless Chrome harness with 50 tracks: page scroll 0, queue list scrolls internally (3375/432 px), links box scrolls (328/98), player tab page scroll 0, format toggle → 'Resolución' + 720p, dark theme applied; native launch smoke: alive, tabs served on :8000, no traceback; native window size 1920x1080 (maximized). Pending: manual click-flows in the native window (the native webview, when launched from a non-interactive shell, drops its socket ~12 s after connect even for a trivial NiceGUI page, so it could not be driven automatically); Windows/Linux only reasoned, not run.

## Acceptance criteria
- `uv run pytest` passes; `uv run main.py` opens themed window.
- Pasting a playlist URL lists all tracks; Mix URL asks before expanding.
- Preview opens the video without leaving the app.

## Progress / Evidence
- Baseline commit on feat/restructure-ui.
- T1 9b827a4, T2/T3 fe6abf9 + docs commit. Not exercised automatically: interactive flows (Mix dialog, download progress, folder picker, clipboard) — manual check pending.

## Next step
Manual run-through of the interactive flows; then push/PR (user decision).
