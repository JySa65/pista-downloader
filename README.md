# YouTube → MP3

Desktop app (NiceGUI, native window) to download YouTube videos, playlists and Mixes as MP3 with yt-dlp.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python 3.14 is installed automatically)
- `ffmpeg` on `PATH` (MP3 conversion and preview clips): `brew install ffmpeg`

## Run

```sh
uv run main.py
```

## Usage

1. Paste one or more URLs (one per line) or press **Pegar**.
2. Press **Cargar**: tracks are listed (no download yet), all checked.
3. Uncheck what you don't want (**Todas** / **Ninguna**), choose the output folder and MP3 quality.
4. Press **Descargar seleccionadas**. **Detener** aborts the current download.

URL types:

- `watch?v=…` → single video.
- `playlist?list=PL…`, `watch?v=…&list=PL…`, `OLAK…` albums → the whole playlist.
- `list=RD…` (YouTube **Mix**) → Mixes are endless, so the app asks whether to take only that video or the Mix up to **Límite Mix** tracks (default 50).

Output:

- Single videos go to the output folder; playlists and Mixes go to `<folder>/<playlist title>/`.
- Downloaded IDs are recorded in `<folder>/.downloaded.txt`; those tracks are skipped next time. Delete a line to re-download.

## Preview

**▶ Ver** opens the YouTube player inside the window. Some videos refuse to play embedded ("video no disponible"); then press **¿No carga? Ver clip de 30 s**, which downloads a low-res 30-second clip (cached in the system temp dir) and plays it locally.

## Development

```sh
uv run pytest -q
```

`youtube_download/core` (URL classification, yt-dlp wrapper) has no UI dependency; `youtube_download/ui` is the NiceGUI app.
