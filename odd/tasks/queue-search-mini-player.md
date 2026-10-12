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
- [ ] T2 Mini player on Descargar — Route: delegated writer (player.py + app.py + tests).

## Progress / evidence
- T1: matches()/visible() in QueueModel (accent+case-insensitive), Queue renders only visible rows, Todas/Ninguna act on visible rows, query kept on session queue. RED: import error; GREEN: pytest 308 passed. Manual UI check pending.

## Next step
T2 writer.
