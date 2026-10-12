# Queue search and mini player on the Descargar tab

## Objective
1. A search box on the Cola (queue) to filter long queues by title/channel.
2. When a song is playing, the Descargar tab shows what is playing with ◀◀ / ▶ ❚❚ / ▶▶ controls,
   like the Reproductor tab, so the user knows and can control it without switching tabs.

## Context
- Built on branch fix/page-reload-keeps-batch (session state refactor, pista/ui/session.py) —
  not merged to main yet; this branch: feat/queue-search-mini-player.
- Queue view: pista/ui/components.py `Queue` (paints the session's QueueModel).
- Player: pista/ui/player.py `Player` (play, play_path, prev, toggle_play, next…).
- Player library already has a search box (pista/core/library.py `_matches`) — reuse its idea.

## Constraints
- Spanish UI copy, English code; match existing component style and theme classes (yt-*).
- Search only filters what is shown: selection, "Todas/Ninguna", counts and downloads are unchanged
  unless stated; the filter must survive row repaints and page reloads only if trivial.
- No new dependencies.

## Tasks
- [x] T1 Queue search box — Route: delegated writer (components.py + app.py + tests).
- [x] T2 Mini player on Descargar — Route: delegated writer (player.py + app.py + tests).

## Progress / evidence
- T1: matches()/visible() in QueueModel (accent+case-insensitive), Queue renders only visible rows, Todas/Ninguna act on visible rows, query kept on session queue. RED: import error; GREEN: pytest 308 passed. Manual UI check pending.
- T2: Player keeps entry/cover + listeners (changed()); now_playing()/play_icon() shared by both views; mini bar above the status line on Descargar, hidden when nothing loaded, title click opens Reproductor. RED: ImportError; GREEN: pytest 313 passed. Manual UI check pending.

- T3 (user report): changing the Biblioteca folder from its menu showed the new folder but "0
  archivos". Cause: Player.reload() created ui.timer in the clicked menu item's slot; build_menu()
  clears the menu, deleting the timer, and NiceGUI's Timer._handle_delete cancels the running
  callback, so load_library never finished. Not related to downloads. Fix: timer anchored to the
  player container. Route inline (one file). No automated test (no NiceGUI UI harness); pytest 313.
- Review (11 files) approved; follow-ups done: Session.run_batch releases the batch slot on
  build/run failure and cancellation (4 tests, RED AttributeError); filtered Queue repaint test;
  ffmpeg warning logged once per app run. pytest 318 passed.

## Next step
User manual check; push when the user says.
