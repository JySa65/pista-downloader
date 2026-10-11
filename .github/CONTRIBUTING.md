# Contributing

Thanks for helping. This is a small desktop app (NiceGUI + yt-dlp), so contributions should stay small and focused.

## Development setup

- [uv](https://docs.astral.sh/uv/). It installs Python 3.14 and every dependency from `uv.lock`.
- `ffmpeg` on `PATH` (macOS: `brew install ffmpeg`, Windows: `winget install ffmpeg`, Debian/Ubuntu: `sudo apt install ffmpeg`).
- Linux only: a pywebview backend (GTK: `sudo apt install python3-gi gir1.2-webkit2-4.1`, or Qt: `uv pip install "pywebview[qt]"`), or run with `--browser`.

```sh
uv sync
uv run main.py            # native window
uv run main.py --browser  # in your browser
```

## Tests

```sh
uv run pytest -q
```

Tests are offline and fast. Changes in behavior are expected to come **test-first**: write or extend a test in `tests/`, watch it fail, then make it pass. Network checks (real downloads) are manual and never part of the test suite.

Never add real music or other copyrighted media to the repository: no IDs, titles or URLs of commercial videos in tests, fixtures, docs or screenshots. Use synthetic IDs (`AAAAAAAAAAA`) or a placeholder like `https://www.youtube.com/watch?v=VIDEO_ID`.

## Project structure

```
main.py                     entry point (only starts the app)
pista/core/                 URL classification, yt-dlp wrapper, library scan, logging, OS helpers — no UI imports
pista/ui/                   NiceGUI app: app.py (page), components.py (queue, dialogs), player.py, theme.py (design tokens)
tests/                      unit tests (core logic and UI invariants)
packaging/                  build.py (PyInstaller + Inno Setup / .dmg / AppImage), LGPL ffmpeg build, icons
.github/workflows/          release builds and the weekly yt-dlp update
```

Keep `core/` free of NiceGUI/UI imports, so the logic stays testable. Prefer small pure functions in `core/` with tests over logic inside UI callbacks.

The UI follows designs made outside this repository (design exports are not versioned). UI copy is in Spanish; code, comments, commits and docs are in English.

## Commits, branches and pull requests

- Branch from `main` (`feat/…`, `fix/…`, `docs/…`, `chore/…`).
- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat(ui): …`, `fix(core): …`, `docs: …`, `test: …`, `chore: …`. Keep tests and docs in the same commit as the behavior they cover.
- Open a pull request against `main` and fill in the template: what changed, how you tested it (commands and OS), screenshots for UI changes, and which platforms (Windows/macOS/Linux) it affects.
- CI builds the installers; please mention anything you could not test on a given OS.

## Releases (maintainers)

1. Bump `version` in `pyproject.toml` (the single source of the version) and run `uv lock`.
2. Tag `vX.Y.Z` on `main` and push the tag. The `Release` workflow checks that the tag matches the version, builds the Windows, macOS and Linux installers and attaches them to a GitHub Release.
3. `Run workflow` on the `Release` workflow builds test installers without publishing.

## License of contributions

This project is licensed under the [GNU General Public License v3.0 or later](../LICENSE). By submitting a contribution you agree that it is licensed under the same terms (inbound = outbound). Make sure you have the right to submit it.

## Conduct and security

Please follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report security problems privately as described in [SECURITY.md](SECURITY.md), not in public issues.
