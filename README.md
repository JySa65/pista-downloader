# YouTube → MP3

Desktop app (NiceGUI, native window) to download YouTube videos, playlists and Mixes as **MP3 or MP4** with yt-dlp, plus a small player for the downloaded MP3s.

## Descargar e instalar

Download the installer for your system from the repository's **Releases** page (latest version at the top). Nothing else is needed: ffmpeg comes bundled.

| System | File | Install |
|--------|------|---------|
| Windows 10/11 (64-bit) | `YouTubeDownload-Setup-<version>.exe` | Run it and follow the wizard (Start Menu entry, optional desktop shortcut, uninstall from *Settings → Apps*). It uses Microsoft Edge WebView2, which ships with Windows 10/11. SmartScreen may warn because the installer is unsigned: *More info → Run anyway*. |
| macOS (Apple Silicon) | `YouTubeDownload-<version>-macos-arm64.dmg` | Open the .dmg and drag **YouTubeDownload** to *Applications*. The app is unsigned, so the first time **right-click → Open → Open** (or *System Settings → Privacy & Security → Open Anyway*). |
| Linux (x86_64, glibc 2.35+) | `YouTubeDownload-<version>-x86_64.AppImage` | `chmod +x YouTubeDownload-*.AppImage` and run it. The Qt web engine is bundled; a desktop with X11/Wayland plus the usual `libnss3`, `libxkbcommon-x11-0` and `libxcb-cursor0` libraries is required. If the AppImage won't start, install `libfuse2` or run it with `--appimage-extract-and-run`. |

The bundled ffmpeg/ffprobe are LGPL builds (Windows/Linux: [BtbN FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) `lgpl` variant; macOS: compiled from the official ffmpeg 8.1.3 and LAME 3.100 sources by `packaging/build_ffmpeg_macos.sh`). Their license texts are shipped next to the binaries (`ffmpeg/LICENSE-*.txt` inside the app).

## Run from source

### Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.14 is installed automatically)
- `ffmpeg` on `PATH` (MP3 conversion, MP4 merging, preview clips). Without it the app starts but refuses to download and says so.

| OS | ffmpeg | Native window |
|----|--------|---------------|
| macOS | `brew install ffmpeg` | built in (WebKit) |
| Windows 10/11 | `winget install ffmpeg` (or `choco install ffmpeg`) | built in (WebView2, ships with Windows) |
| Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` | GTK: `sudo apt install python3-gi gir1.2-webkit2-4.1`, or Qt: `uv pip install "pywebview[qt]"` |

If the native window can't be used (e.g. Linux without GTK/Qt) the app opens in your browser instead. You can force that with `uv run main.py --browser` or `YTMP3_BROWSER=1`.

"Pegar" (the `+` button with an empty field) reads the clipboard with `pbpaste` (macOS), PowerShell `Get-Clipboard` (Windows) or `wl-paste` / `xclip` / `xsel` (Linux). If none is available, paste into the field with Ctrl/Cmd+V.

### Start

```sh
uv run main.py
```

The window opens maximized.

## Descargar tab

1. Paste a link in the field and press Enter (or `+`; with the field empty, `+` pastes from the clipboard). Each link shows its type: Video, Playlist or Mix.
2. Press **Cargar**: the tracks are listed (nothing is downloaded yet), all checked.
3. Uncheck what you don't want (**Todas** / **Ninguna**; click a row to toggle). Choose the output folder, **Formato** (Audio · MP3 / Video · MP4) and the quality (kbps for MP3, resolution for MP4).
4. Press **Descargar seleccionadas**. Each row shows its progress and status; **Detener** aborts the current download.

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

Lists the MP3s in the download folder (or another folder from the folder menu, including subfolders), with search, play/pause, previous/next, Aleatorio, Repetir, a seek bar and volume. The artist is taken from `Artist - Title` file names, otherwise the subfolder name.

**Modo oscuro / Modo claro** in the title bar switches the theme.

## Development

```sh
uv run pytest -q
```

`youtube_download/core` (URL classification, yt-dlp wrapper, library scan, OS helpers) has no UI dependency. `youtube_download/ui` is the NiceGUI app; the design tokens live in `ui/theme.py`.

## Publicar una versión

1. Bump `version` in `pyproject.toml` (the single source of the version; the app shows it in the title bar) and commit.
2. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`. The tag **must** equal `v` + the pyproject version, otherwise the workflow fails.
3. `.github/workflows/release.yml` builds the Windows installer, the macOS .dmg and the Linux AppImage on GitHub-hosted runners, runs the tests, checks that the bundled ffmpeg is not GPL, and attaches the three files to a GitHub Release for that tag.
4. For a test build without a release, run the **Release** workflow manually (*Actions → Release → Run workflow*); the installers appear as workflow artifacts.

Local build for the current OS: `uv sync --group build && uv run python packaging/build.py` (output in `dist/`). On Windows it needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`ISCC.exe`); on macOS the first build compiles ffmpeg (~2 min), which needs the Xcode command line tools.

**yt-dlp updates.** YouTube regularly breaks old yt-dlp versions. `.github/workflows/update-yt-dlp.yml` runs every Monday (or manually), upgrades yt-dlp in `uv.lock` and opens a PR. Merge it and tag a new version to ship it. The repository setting *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests* must be enabled. PRs opened with the workflow token don't trigger other workflows, so run tests locally or re-run them from the PR if needed.

**ffmpeg pins.** The BtbN download URLs and SHA256 sums live in `packaging/build.py`; BtbN eventually deletes old autobuilds, so when that download 404s, pick a newer `autobuild-*` release (an `ffmpeg-n<ver>-…-lgpl-<ver>` asset) and update the URL and checksum.
