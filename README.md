# YouTube → MP3

Desktop app (NiceGUI, native window) to download YouTube videos, playlists and Mixes as **MP3 or MP4** with yt-dlp, plus a small player for the downloaded MP3s.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.14 is installed automatically)
- `ffmpeg` on `PATH` (MP3 conversion, MP4 merging, preview clips). Without it the app starts but refuses to download and says so.

| OS | ffmpeg | Native window |
|----|--------|---------------|
| macOS | `brew install ffmpeg` | built in (WebKit) |
| Windows 10/11 | `winget install ffmpeg` (or `choco install ffmpeg`) | built in (WebView2, ships with Windows) |
| Linux (Debian/Ubuntu) | `sudo apt install ffmpeg` | GTK: `sudo apt install python3-gi gir1.2-webkit2-4.1`, or Qt: `uv pip install "pywebview[qt]"` |

If the native window can't be used (e.g. Linux without GTK/Qt) the app opens in your browser instead. You can force that with `uv run main.py --browser` or `YTMP3_BROWSER=1`.

"Pegar" (the `+` button with an empty field) reads the clipboard with `pbpaste` (macOS), PowerShell `Get-Clipboard` (Windows) or `wl-paste` / `xclip` / `xsel` (Linux). If none is available, paste into the field with Ctrl/Cmd+V.

## Run

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
