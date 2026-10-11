# YouTube pacing and PO tokens

## Objective
Reduce YouTube's "Sign in to confirm you're not a bot" check during batch downloads.

## Problem / why
The user hits the bot check after a few mixes (~20 tracks each), well below yt-dlp's documented
guest limit (~300 videos/hour). yt-dlp recommends 5–10 s between downloads and a PO Token
provider plugin (https://github.com/yt-dlp/yt-dlp/wiki/Extractors, PO-Token-Guide).

## Scope
- T1: app-side pacing of 5–10 s between tracks, always visible to the user (status line + log).
- T2: PO Token provider (bgutil) bundled with zero user setup — pending research outcome.

## Constraints
- Stop must interrupt the wait (reuse `BatchRunner._wait`).
- `poll()` overwrites the status line while `runner.current` is set: show the wait while it is None.
- Generated artifacts in English; UI copy in Spanish (existing convention).

## Tasks
- [x] T1 Pacing 5–10 s between downloads with visible message
  - Route: delegated (writer trigger: queue.py + downloader.py + tests are 2+ non-trivial files)
  - Acceptance: no wait before the first download of a run; random 5–10 s wait before each later
    download; status line and log say why; Stop interrupts; yt-dlp per-format sleep removed
    (no double sleep on MP4); tests updated (tests/test_pacing.py).
  - Checks: `.venv/bin/python -m pytest -q --ignore=tests/chaos`
- [ ] T2 PO Token provider (bgutil) — approved by user (2026-10-11), keep updated like yt-dlp
  - [x] T2a Prototype on macOS: plugin + server (pinned 2.0.2) + bundled deno, script mode; prove a
        token is generated in a real yt-dlp run (log shows bgutil:script provider). Route: delegated.
  - [x] T2b Integrate in dev env: dependency pinned in pyproject/uv.lock, server fetched by a script,
        extractor_args server_home in base_opts only when the server is present; tests.
  - [ ] T2c Packaging: build.py ships yt-dlp-plugins/ + server (src + node_modules) per OS; CI.
  - [x] T2d Auto-update: extend .github/workflows/update-yt-dlp.yml to bump bgutil (plugin + server).
  - Findings: pip wheel is only the Python plugin; token generator (server/src + node_modules with
    native `canvas`) must be shipped per OS (mac arm64/x64, Windows). Script mode reuses the bundled
    deno via js_runtimes (needs deno >= 2.4.3; bundled 2.9.7). PyInstaller: plugins must be real
    files on disk (yt-dlp-plugins/ next to the executable). Latest 2.0.2 (2026-10-07). README: does
    not guarantee bypassing bot checks. Unverified: canvas loading under deno in a frozen app.

## Progress / evidence
- Exploration done (pacing, logger, status flow, packaging mapped).
- T1 done in 451683f: RED ImportError PACE_MAX; GREEN `pytest -q` (incl. chaos) 287 passed.
  No pause after cooldown/retry delay (already a pause). Chaos hang tests use pace=(0, 0).
  Review assess: medium, review_due=false (under_budget) — pending in slice.

- T2a done (scratchpad, no repo change): macOS arm64 + bundled deno 2.9.7 + bgutil 2.0.2 script mode
  generated gvs/subs tokens for mweb (provider `bgutil:script-deno`) and downloaded bestaudio with
  `pot=` param, no 403. canvas ships prebuilt (no compiler). server/ = 174M, ~93M without devDeps.
  ~6 s per new video token (bound to video id); cache 6 h. http-provider ping error logs at normal
  level (hide it). Needs src/, node_modules/ (symlinks), package.json, deno.json; writable cache dir.
- T2b/T2d done: plugin dep >=2.0.2 in uv.lock; packaging/fetch_pot_server.py fetches server at the
  installed plugin version into vendor/ (reachability prune → 88M, idempotent). base_opts adds
  server_home + player_client ['default','mweb'] only when deno + server exist (default clients
  visionos/web never request a PO token). bgutil http ping message downgraded to DEBUG. Weekly
  workflow bumps yt-dlp + bgutil in one PR. GREEN: pytest -q 293 passed; real run retrieved gvs token.

## Next step
T2c packaging (macOS local build + CI on Windows/Linux).
