# Page reload keeps the running batch

## Objective
After the window reloads the page (e.g. Mac locked/asleep longer than NiceGUI's reconnect window),
Pista must show the running batch again: queue rows with states/progress, status line, log, busy
buttons, summary — instead of a blank page while the download keeps running invisibly.

## Problem / why
Evidence (pista.log 2026-10-11): batch started 20:23; at 21:08:12 `index()` ran again (startup log
line) after unlock; the batch kept downloading (50 ok / 7 failed) bound to the dead page. All UI
state lives in `index()` closures (pista/ui/app.py:77-85: links, link_errors, fmt, quality, busy,
log_lines, last_summary, runner) and the Queue component, so a new page starts empty. A second batch
started from the blank page would run in parallel with the invisible one.

## Scope
- T1: raise NiceGUI `reconnect_timeout` in both `ui.run` calls so a normal lock/sleep doesn't drop
  the page.
- T2: keep session state outside the page (single-user desktop app → one app-level session): links,
  link errors, format/quality, queue model/rows state, log lines, last summary, runner, busy. A new
  page renders from it; the running BatchRunner's callbacks (status, log, on_progress, row updates,
  end-of-batch summary/dialog) reach whichever page is currently open (or none, without crashing).
  Only one batch can run at a time across pages.

## Constraints
- UI copy Spanish, code English; match app.py style. No new dependencies.
- Old page's deleted elements must never be touched (existing BatchRunner safe-callback wrappers).

## Tasks
- [x] T1 reconnect_timeout — Route: inline (one mechanical line per ui.run).
- [x] T2 app-level session state + page reattach — Route: delegated writer (app.py + components.py,
      2+ non-trivial files). Checks: `.venv/bin/python -m pytest -q`; manual: start a batch, reload
      the page (browser mode), state reappears and progress continues.

## Progress / evidence
- T1: RECONNECT_TIMEOUT = 3600 passed to both ui.run calls (NiceGUI default 3.0 s, verified in ui_run.py:59). pytest 227 passed.
- T1 review: approved (suggestion: no test asserts ui.run gets reconnect_timeout — not added,
  ui.run is only called from main()).
- T2: pista/ui/session.py SESSION (state + attached pages, newest page is current, begin() single
  batch guard); Queue paints the session model; index() attaches and detaches on client delete.
  RED: test_session collection error; GREEN: pytest -q 302 passed. Simulated reload (NiceGUI user
  simulation, scratch) showed rows/progress/status/log and the summary dialog on the new page; it
  caught a NameError (fmt_short defined after Queue) that was fixed. Not verified in a real window.
  "Descargar seleccionadas" while busy still adds to the running batch (never a parallel one).

## Next step
User manual check in a real window (reload mid-batch), then merge to main.
