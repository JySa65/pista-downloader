"""yt-dlp wrapper: list tracks without downloading, download one track as MP3/MP4."""
import logging
import threading
from collections.abc import Callable
from pathlib import Path

import yt_dlp
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import DownloadCancelled, download_range_func, sanitize_filename

from .models import Track
from .plan import video_sizes
from .system import find_deno, find_ffmpeg
from .urls import video_id, video_url

Cancelled = DownloadCancelled  # raised by download() when cancel_event is set

log = logging.getLogger("pista.yt_dlp")

ARCHIVES = {"audio": ".downloaded-audio.txt", "video": ".downloaded-video.txt"}


def format_opts(fmt: str, quality: str) -> dict:
    """yt-dlp options for 'audio' (MP3 at `quality` kbps) or 'video' (MP4 up to `quality`, e.g. '720p', '4K')."""
    if fmt == "audio":
        return {
            "format": "bestaudio/best",
            "writethumbnail": True,  # cover art: YouTube thumbnail -> jpg -> embedded in the MP3, plus tags
            "postprocessors": [
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality},
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail"},
            ],
        }
    if fmt == "video":
        h = 2160 if quality.upper() == "4K" else int(quality.rstrip("p"))
        return {
            "format": f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/b[height<={h}]",
            "merge_output_format": "mp4",
        }
    raise ValueError(f"unknown format: {fmt}")


class _Logger:
    """Routes yt-dlp output to the app log (the file keeps warnings/errors yt-dlp would print)."""

    def debug(self, msg: str) -> None:
        # With quiet=True yt-dlp sends its normal screen output here too; keep it (it explains 403s etc.).
        (log.debug if msg.startswith("[debug] ") else log.info)(msg)

    def info(self, msg: str) -> None:
        log.info(msg)

    def warning(self, msg: str) -> None:
        log.warning(msg)

    def error(self, msg: str) -> None:
        log.error(msg)


def base_opts(ffmpeg: str | None, deno: str | None, logger: object | None) -> dict:
    """Options shared by every yt-dlp call: bundled tools, retries, quiet console, portable names."""
    opts = {
        "quiet": True,
        "noprogress": True,
        "windowsfilenames": True,  # portable names on every OS (reserved chars, trailing dots/spaces)
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 3,
    }
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    if logger is not None:
        opts["logger"] = logger
    return opts


def _ydl(extra: dict) -> yt_dlp.YoutubeDL:
    """The single place that builds a YoutubeDL."""
    ffmpeg = find_ffmpeg()
    # yt-dlp only honors `ffmpeg_location` in some code paths (e.g. picking the downloader for
    # partial/section downloads checks this context var, which only its CLI sets). Set it in this thread.
    FFmpegPostProcessor._ffmpeg_location.set(ffmpeg)
    return yt_dlp.YoutubeDL({**base_opts(ffmpeg, find_deno(), _Logger()), **extra})


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
        video_sizes=video_sizes(entry.get("formats") or []),  # only full (non-flat) extraction has formats
    )


def list_tracks(url: str, kind: str, mix_limit: int = 50) -> list[Track]:
    """Fast listing via extract_flat. kind: 'video' | 'playlist' | 'mix'."""
    opts = {"skip_download": True}
    if kind == "video":
        url, opts["noplaylist"] = video_url(url), True
    else:
        opts["extract_flat"] = "in_playlist"
        if kind == "mix":
            opts["playlistend"] = mix_limit
    with _ydl(opts) as ydl:
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
        "noplaylist": True,
        "outtmpl": str(target / "%(title)s.%(ext)s"),
        "download_archive": str(Path(outdir) / ARCHIVES[fmt]),
        "progress_hooks": [hook],
    }
    with _ydl(opts) as ydl:
        info = ydl.extract_info(track.url, download=True)
    downloads = (info or {}).get("requested_downloads") or []
    if not downloads:
        return None  # skipped: already in download archive
    on_progress(100.0, "Listo")
    return downloads[0]["filepath"]


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
        "outtmpl": str(path.with_suffix(".%(ext)s")),
        "noplaylist": True,
    }
    with _ydl(opts) as ydl:
        ydl.download([video_url(url)])
    return path
