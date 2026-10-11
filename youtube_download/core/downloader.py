"""yt-dlp wrapper: list tracks without downloading, download one track as MP3."""
import threading
from collections.abc import Callable
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadCancelled, download_range_func, sanitize_filename

from .models import Track
from .system import find_ffmpeg
from .urls import video_id, video_url

Cancelled = DownloadCancelled  # raised by download() when cancel_event is set

ARCHIVES = {"audio": ".downloaded-audio.txt", "video": ".downloaded-video.txt"}


def format_opts(fmt: str, quality: str) -> dict:
    """yt-dlp options for 'audio' (MP3 at `quality` kbps) or 'video' (MP4 up to `quality`, e.g. '720p', '4K')."""
    if fmt == "audio":
        return {
            "format": "bestaudio/best",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality}
            ],
        }
    if fmt == "video":
        h = 2160 if quality.upper() == "4K" else int(quality.rstrip("p"))
        return {
            "format": f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/b[height<={h}]",
            "merge_output_format": "mp4",
        }
    raise ValueError(f"unknown format: {fmt}")


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
    outdir: str | Path,
    quality: str = "192",
    subfolder: str = "",
    on_progress: Callable[[float, str], None] = lambda pct, msg: None,
    cancel_event: threading.Event | None = None,
    fmt: str = "audio",
) -> str | None:
    """Download track as MP3 or MP4. Returns the real file path, or None if already archived.

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
            on_progress(95.0, "Procesando…")

    target = Path(outdir) / sanitize_filename(subfolder) if subfolder else Path(outdir)
    opts = {
        **format_opts(fmt, quality),
        **_ffmpeg_opts(),
        "noplaylist": True,
        "windowsfilenames": True,  # portable names on every OS (reserved chars, trailing dots/spaces)
        "outtmpl": str(target / "%(title)s.%(ext)s"),
        "download_archive": str(Path(outdir) / ARCHIVES[fmt]),
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


def _ffmpeg_opts() -> dict:
    location = find_ffmpeg()
    return {"ffmpeg_location": location} if location else {}


def preview_clip_path(url: str, dest_dir: str | Path) -> Path:
    return Path(dest_dir) / f"{video_id(url)}.mp4"


def preview_clip(url: str, dest_dir: str | Path, seconds: int = 30) -> Path:
    """Low-res mp4 (video+audio) of the first `seconds`, cached per video id."""
    path = preview_clip_path(url, dest_dir)
    if path.exists():
        return path
    opts = {
        "format": "bv*[height<=360][ext=mp4]+ba[ext=m4a]/b[height<=360]",
        "download_ranges": download_range_func(None, [(0, seconds)]),
        "merge_output_format": "mp4",
        **_ffmpeg_opts(),
        "windowsfilenames": True,
        "outtmpl": str(path.with_suffix(".%(ext)s")),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([video_url(url)])
    return path
