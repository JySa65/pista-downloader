# Pista

**Descarga audio y video.**

[![Release](https://img.shields.io/github/v/release/JySa65/pista-downloader?sort=semver)](https://github.com/JySa65/pista-downloader/releases/latest)
[![License: GPL v3](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)
[![Build](https://github.com/JySa65/pista-downloader/actions/workflows/release.yml/badge.svg)](https://github.com/JySa65/pista-downloader/actions/workflows/release.yml)

**Pista** is a free, open-source desktop app for Windows, macOS and Linux that downloads YouTube videos, playlists and Mixes as **MP3 or MP4** with [yt-dlp](https://github.com/yt-dlp/yt-dlp), and includes a small player for the downloaded files. The installers bundle everything they need (ffmpeg, a JavaScript runtime), so there is nothing else to install.

**Pista** es una aplicación de escritorio libre y gratuita para Windows, macOS y Linux que descarga videos, listas y Mixes de YouTube como **MP3 o MP4** con yt-dlp, con un reproductor para lo descargado.

> **Aviso legal / Legal notice** — see [below](#aviso-legal--legal-notice).

## Descargar e instalar

> Pista was called «YouTube → MP3» up to v0.2.x. Installing Pista on Windows replaces the old app (same installer id); its logs and preview cache move to the new folder on first run. On macOS, drag the old «YouTubeDownload» app to the Trash. Your downloads and the `.downloaded-*.txt` files in your music folder are untouched.

Download the installer for your system from the repository's **Releases** page (latest version at the top). Nothing else is needed: ffmpeg comes bundled.

| System | File | Install |
|--------|------|---------|
| Windows 10 y 11 (64 bits) | `Pista-Setup-<version>.exe` | Run it and follow the wizard (Start Menu entry, optional desktop shortcut, uninstall from *Settings → Apps*). The app uses Microsoft Edge WebView2: Windows 11 includes it, and on Windows 10 the installer checks for it and, if missing, installs it with Microsoft's bootstrapper (needs internet once). SmartScreen may warn because the installer is unsigned: *More info → Run anyway*. |
| macOS (Apple Silicon) | `Pista-<version>-macos-arm64.dmg` | Open the .dmg and drag **Pista** to *Applications*. The app is unsigned, so the first time **right-click → Open → Open** (or *System Settings → Privacy & Security → Open Anyway*). |
| Linux (x86_64, glibc 2.35+) | `Pista-<version>-x86_64.AppImage` | `chmod +x Pista-*.AppImage` and run it. The Qt web engine is bundled; a desktop with X11/Wayland plus the usual `libnss3`, `libxkbcommon-x11-0` and `libxcb-cursor0` libraries is required. If the AppImage won't start, install `libfuse2` or run it with `--appimage-extract-and-run`. |

The bundled ffmpeg/ffprobe are LGPL builds (Windows/Linux: [BtbN FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) `lgpl` variant; macOS: compiled from the official ffmpeg 8.1.3 and LAME 3.100 sources by `packaging/build_ffmpeg_macos.sh`). Their license texts are shipped next to the binaries (`ffmpeg/LICENSE-*.txt` inside the app).

YouTube now requires solving JavaScript challenges; without a JS runtime yt-dlp falls back to limited clients and downloads can fail with **HTTP 403**. The installers therefore bundle [Deno](https://deno.com) (MIT, `deno/LICENSE-deno.txt`) and yt-dlp's challenge-solver scripts ([yt-dlp-ejs](https://github.com/yt-dlp/ejs), Unlicense/MIT/ISC). From source, `uv sync` installs both (`yt-dlp[default,deno]`).

## Run from source

### Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.14 is installed automatically)
- `ffmpeg` on `PATH` (MP3 conversion, MP4 merging, preview clips). Without it the app starts but refuses to download and says so.

| OS | ffmpeg | Native window |
|----|--------|---------------|
| macOS | `brew install ffmpeg` | built in (WebKit) |
| Windows 10/11 (64-bit) | `winget install ffmpeg` (or `choco install ffmpeg`) | WebView2 (included in Windows 11; on Windows 10 install the [Evergreen runtime](https://developer.microsoft.com/microsoft-edge/webview2/) if missing) |
| Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` | GTK: `sudo apt install python3-gi gir1.2-webkit2-4.1`, or Qt: `uv pip install "pywebview[qt]"` |

If the native window can't be used (e.g. Linux without GTK/Qt) the app opens in your browser instead. You can force that with `uv run main.py --browser` or `PISTA_BROWSER=1`.

**Pegar** reads the clipboard with `pbpaste` (macOS), PowerShell `Get-Clipboard` (Windows) or `wl-paste` / `xclip` / `xsel` (Linux). If none is available, paste into the field with Ctrl/Cmd+V.

### Start

```sh
uv run main.py
```

The window opens maximized.

## Descargar tab

1. Paste or type links in the **Links** box (one per line), then press **+ Añadir** or Ctrl/⌘+Enter. **Pegar** adds the links in the clipboard directly. Each link shows its type: Video, Playlist or Mix.
2. Press **Cargar**: the tracks are added to the **Cola** (nothing is downloaded yet), all checked. While a download is running the button reads **Cargar a la cola**: new tracks go to the end of the running batch and get a «Nuevo» tag.
3. Uncheck what you don't want (**Todas** / **Ninguna**; click a row to toggle). **Limpiar cola** removes finished, failed and unchecked rows. Choose the output folder, **Formato** (Audio · MP3 / Video · MP4) and the quality.
4. Press **Descargar seleccionadas**. Each row shows its status (En cola, %, Listo, Ya estaba, Reintentando (n/3), Error, Detenida); **Detener** aborts the current download.
5. Failed tracks are retried once automatically 10 s after the batch; after that, a red row shows the short reason and **↻ Reintentar**.
6. When the batch ends (or is stopped) a **summary** shows downloaded / already there / failed / stopped, total size, time and folder, with **Ir al reproductor**, **Abrir carpeta** and **Reintentar fallidas**. **Ver resumen** reopens it.

**Registro** (below the queue) shows the last line; **Expandir** shows the full lines and **Abrir registro** the whole log file, with a button to show it in Finder / Explorer / the file manager. The file is `pista.log` (rotating, 2 MB × 4) in the per-user cache folder: `~/Library/Caches/pista/logs` (macOS), `%LOCALAPPDATA%\pista\Cache\logs` (Windows), `~/.cache/pista/logs` (Linux). Your home folder appears as `~`. It includes yt-dlp's own warnings and errors, so attach it when reporting a problem.

URL types:

- `watch?v=…` → single video.
- `playlist?list=PL…`, `watch?v=…&list=PL…`, `OLAK…` albums → the whole playlist.
- `list=RD…` (YouTube **Mix**) → Mixes never end, so the app asks whether to take only that video or the Mix, up to **Canciones por Mix** tracks (1–50).

Output:

- The default folder is `~/Music`, or `~/Downloads`, or your home folder (the first one that exists).
- Single videos go to the output folder. Playlists and Mixes go to `<folder>/<playlist title>/`. File names are made Windows-safe on every OS.
- Downloaded IDs are recorded per format in `<folder>/.downloaded-audio.txt` and `<folder>/.downloaded-video.txt`, and those tracks are skipped next time. Delete a line to download it again.

**▶ Ver** opens the YouTube player inside the app. Some videos refuse to play embedded; then press **¿No carga? Ver clip de 30 s**, which downloads a low-res 30-second clip (cached in the system temp dir) and plays it locally. **Abrir en el navegador** opens the video on YouTube.

## Reproductor tab

Lists the MP3 and MP4 files in the download folder (or another folder from the folder menu, including subfolders), with search, play/pause, previous/next, Aleatorio, Repetir, a seek bar and volume. MP3s show the cover embedded at download time (the YouTube thumbnail, plus title/artist tags); MP4s play in the same space, with **⛶ Pantalla completa** (Esc exits). The artist is taken from `Artist - Title` file names, otherwise the subfolder name.

**Modo oscuro / Modo claro** in the title bar switches the theme.

## Development

```sh
uv run pytest -q
```

`pista/core` (URL classification, yt-dlp wrapper, library scan, OS helpers) has no UI dependency. `pista/ui` is the NiceGUI app; the design tokens live in `ui/theme.py`.

## Publicar una versión

1. Bump `version` in `pyproject.toml` (the single source of the version; the app shows it in the title bar) and commit.
2. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`. The tag **must** equal `v` + the pyproject version, otherwise the workflow fails.
3. `.github/workflows/release.yml` builds the Windows installer, the macOS .dmg and the Linux AppImage on GitHub-hosted runners, runs the tests, checks that the bundled ffmpeg is not GPL, and attaches the three files to a GitHub Release for that tag.
4. For a test build without a release, run the **Release** workflow manually (*Actions → Release → Run workflow*); the installers appear as workflow artifacts.

Local build for the current OS: `uv sync --group build && uv run python packaging/build.py` (output in `dist/`). On Windows it needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`ISCC.exe`); on macOS the first build compiles ffmpeg (~2 min), which needs the Xcode command line tools.

**yt-dlp updates.** YouTube regularly breaks old yt-dlp versions. `.github/workflows/update-yt-dlp.yml` runs every Monday (or manually), upgrades yt-dlp in `uv.lock` and opens a PR. Merge it and tag a new version to ship it. The repository setting *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests* must be enabled. PRs opened with the workflow token don't trigger other workflows, so run tests locally or re-run them from the PR if needed.

**ffmpeg pins.** The BtbN download URLs and SHA256 sums live in `packaging/build.py`; BtbN eventually deletes old autobuilds, so when that download 404s, pick a newer `autobuild-*` release (an `ffmpeg-n<ver>-…-lgpl-<ver>` asset) and update the URL and checksum.

## Aviso legal / Legal notice

**ES —** Esta es una herramienta para uso personal. Cada usuario es responsable de cumplir los [Términos de servicio de YouTube](https://www.youtube.com/t/terms) y las leyes de derechos de autor de su país. Descarga solo contenido sobre el que tengas derechos o permiso (por ejemplo, tus propios videos o material con licencia libre). Este proyecto no está afiliado, asociado, respaldado ni patrocinado por YouTube ni por Google LLC; «YouTube» es una marca de Google LLC y se menciona solo para describir con qué sitio funciona la aplicación.

**EN —** This is a tool for personal use. Users are responsible for complying with [YouTube's Terms of Service](https://www.youtube.com/t/terms) and the copyright laws of their country. Only download content you own or have permission to download (for example your own uploads or openly licensed material). This project is not affiliated with, associated with, endorsed or sponsored by YouTube or Google LLC; "YouTube" is a trademark of Google LLC and is used only to describe which site the app works with.

## Licencia / License

[GNU General Public License v3.0 or later](LICENSE). The installers also contain third-party components under their own licenses; see [THIRD_PARTY_NOTICES.md](.github/THIRD_PARTY_NOTICES.md).

## Contribuir / Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) and the [Code of Conduct](.github/CODE_OF_CONDUCT.md). Report security issues privately as described in [SECURITY.md](.github/SECURITY.md). Bugs: use **Reportar un problema** in the app, which opens the bug form with your version and OS filled in.
