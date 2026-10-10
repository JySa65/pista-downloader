"""yt-dlp wrapper: list tracks without downloading, download one track as MP3."""
import os
import threading
from collections.abc import Callable

import yt_dlp
from yt_dlp.utils import DownloadCancelled, sanitize_filename

from .models import Track
from .urls import video_url

Cancelled = DownloadCancelled  # raised by download() when cancel_event is set

ARCHIVE_NAME = ".downloaded.txt"


def _thumbnail(entry: dict) -> str | None:
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = entry.get("thumbnails") or []
    return thumbs[-1].get("url") if thumbs else None


def _track(entry: dict, playlist: str = "") -> Track:
    vid = entry.get("id") or ""
    return Track(
        id=vid,
        title=entry.get("title") or "(sin título)",
        channel=entry.get("channel") or entry.get("uploader") or "?",
        duration=entry.get("duration"),
        url=f"https://www.youtube.com/watch?v={vid}" if vid else entry.get("url", ""),
        thumbnail=_thumbnail(entry),
        playlist=playlist,
    )


def list_tracks(url: str, kind: str, mix_limit: int = 50) -> list[Track]:
    """Fast listing via extract_flat. kind: 'video' | 'playlist' | 'mix'."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    if kind == "video":
        url, opts["noplaylist"] = video_url(url), True
    else:
        opts["extract_flat"] = "in_playlist"
        if kind == "mix":
            opts["playlistend"] = mix_limit
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") != "playlist":
        return [_track(info)]
    title = info.get("title") or info.get("id") or "playlist"
    return [_track(e, title) for e in info.get("entries") or [] if e]


def download(
    track: Track,
    outdir: str,
    kbps: str = "192",
    subfolder: str = "",
    on_progress: Callable[[float, str], None] = lambda pct, msg: None,
    cancel_event: threading.Event | None = None,
) -> str | None:
    """Download track as MP3. Returns the real file path, or None if already archived.

    Raises Cancelled when cancel_event is set mid-download.
    """
    def hook(d):
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = d.get("downloaded_bytes", 0) / total * 100 if total else 0.0
            on_progress(pct, f"Descargando… {pct:0.1f}%")
        elif d.get("status") == "finished":
            on_progress(95.0, "Convirtiendo a MP3…")

    target = os.path.join(outdir, sanitize_filename(subfolder)) if subfolder else outdir
    opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "outtmpl": os.path.join(target, "%(title)s.%(ext)s"),
        "download_archive": os.path.join(outdir, ARCHIVE_NAME),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": kbps}
        ],
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 5,
        "fragment_retries": 5,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(track.url, download=True)
    downloads = (info or {}).get("requested_downloads") or []
    if not downloads:
        return None  # skipped: already in download archive
    on_progress(100.0, "Listo")
    return downloads[0]["filepath"]
