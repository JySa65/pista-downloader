"""yt-dlp wrapper: list tracks without downloading, download one track as MP3/MP4."""
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import DownloadCancelled, download_range_func, sanitize_filename

from contextlib import contextmanager

from .batch import is_rate_limited
from .breaker import GATE
from .models import Track
from .plan import video_sizes
from .progress import phase_for_postprocessor
from .system import find_deno, find_ffmpeg, find_pot_server
from .urls import is_youtube, video_id, video_url

Cancelled = DownloadCancelled  # raised by download() when cancel_event is set

log = logging.getLogger("pista.yt_dlp")

# Only YouTube extractors: yt-dlp's generic extractor would otherwise read metadata from any web page.
ALLOWED_EXTRACTORS = ["youtube", "youtube:tab", "youtube:playlist", "youtubeytbe"]

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


# bgutil's HTTP provider pings a server Pista never runs (it uses the script provider): not a problem.
_EXPECTED_NOISE = "This is expected if you are using the script method."


class _Logger:
    """Routes yt-dlp output to the app log (the file keeps warnings/errors yt-dlp would print)."""

    def debug(self, msg: str) -> None:
        # With quiet=True yt-dlp sends its normal screen output here too; keep it (it explains 403s etc.).
        (log.debug if msg.startswith("[debug] ") or _EXPECTED_NOISE in msg else log.info)(msg)

    def info(self, msg: str) -> None:
        (log.debug if _EXPECTED_NOISE in msg else log.info)(msg)

    def warning(self, msg: str) -> None:
        (log.debug if _EXPECTED_NOISE in msg else log.warning)(msg)

    def error(self, msg: str) -> None:
        log.error(msg)


def _retry_sleep(attempt: int) -> float:
    return min(60.0, 2.0 ** attempt)


_cookie_browser: str | None = None  # set from the UI option; None = don't use browser cookies


def set_cookie_browser(browser: str | None) -> None:
    """Use this browser's YouTube session for every yt-dlp call (listing, download, preview), or None."""
    global _cookie_browser
    _cookie_browser = browser


def base_opts(ffmpeg: str | None, deno: str | None, logger: object | None, cookies_browser: str | None = None,
              pot_server: Path | str | None = None) -> dict:
    """Options shared by every yt-dlp call: bundled tools, retries, quiet console, portable names."""
    opts = {
        "quiet": True,
        "noprogress": True,
        "no_color": True,  # no ANSI codes in messages we log or show
        "windowsfilenames": True,  # portable names on every OS (reserved chars, trailing dots/spaces)
        "retries": 10,  # media HTTP retries only cover network errors/5xx: keep resilience for drops
        "fragment_retries": 10,
        "extractor_retries": 1,  # a 429/bot check is handled by the global breaker, not by hammering
        # Pacing: ~1 s between extraction requests. The 5–10 s pause between downloads is BatchRunner's
        # (visible in the UI); yt-dlp's own sleep_interval would also sleep before each format (twice per MP4).
        "sleep_interval_requests": 1,
        # yt-dlp retries immediately by default; back off instead (1, 2, 4, … s, capped).
        "retry_sleep_functions": {kind: _retry_sleep for kind in ("http", "fragment", "extractor")},
        "allowed_extractors": ALLOWED_EXTRACTORS,
    }
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
        if pot_server:
            # PO Tokens (YouTube's anti-bot proof) generated locally by bgutil's script, run with the same deno.
            # yt-dlp's default clients never request one; mweb does, so add it (~6 s per new video, cached 6 h).
            opts.setdefault("extractor_args", {}).update({
                "youtubepot-bgutilscript": {"server_home": [str(pot_server)]},
                "youtube": {"player_client": ["default", "mweb"]},
            })
    if logger is not None:
        opts["logger"] = logger
    if cookies_browser:
        # yt-dlp reads the cookies in memory for its requests; Pista never stores or logs them.
        opts["cookiesfrombrowser"] = (cookies_browser,)
    return opts


def _ydl(extra: dict) -> yt_dlp.YoutubeDL:
    """The single place that builds a YoutubeDL."""
    ffmpeg = find_ffmpeg()
    # yt-dlp only honors `ffmpeg_location` in some code paths (e.g. picking the downloader for
    # partial/section downloads checks this context var, which only its CLI sets). Set it in this thread.
    FFmpegPostProcessor._ffmpeg_location.set(ffmpeg)
    return yt_dlp.YoutubeDL({**base_opts(ffmpeg, find_deno(), _Logger(), _cookie_browser, find_pot_server()), **extra})


def _thumbnail(entry: dict) -> str | None:
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = entry.get("thumbnails") or []
    return thumbs[-1].get("url") if thumbs else None


def _entry_id(entry: dict) -> str:
    """Video id from the entry, or from its YouTube URL; '' if there is none (the entry is skipped)."""
    vid = entry.get("id")
    if isinstance(vid, str) and vid:
        return vid
    url = entry.get("url")
    return (video_id(url) or "") if isinstance(url, str) and is_youtube(url) else ""


def _track(entry: dict, playlist: str = "") -> Track:
    vid = _entry_id(entry)
    return Track(
        id=vid,
        title=entry.get("title") or "(sin título)",
        channel=entry.get("channel") or entry.get("uploader") or "?",
        duration=entry.get("duration"),
        url=f"https://www.youtube.com/watch?v={vid}",
        thumbnail=_thumbnail(entry),
        playlist=playlist,
        video_sizes=video_sizes(entry.get("formats") or []),  # only full (non-flat) extraction has formats
    )


class ReliableThumbnail(PostProcessor):
    """Keep only YouTube's always-present hqdefault.jpg as the cover candidate.

    yt-dlp otherwise probes thumbnails from the largest down, one request per missing size (7 extra
    requests measured for an old video). Runs at 'pre_process', before thumbnails are written.
    """

    def run(self, info):
        thumbs = info.get("thumbnails") or []
        keep = [t for t in thumbs if "/hqdefault.jpg" in (t.get("url") or "")]
        if keep:
            info["thumbnails"] = keep[:1]
        return [], info


@contextmanager
def _youtube():
    """Every YouTube operation: one at a time, none during a cooldown; a rate limit pauses everything."""
    with GATE.use():
        try:
            yield
        except Exception as e:
            if is_rate_limited(str(e)):
                GATE.breaker.trip()
            raise
        GATE.breaker.record_success()


def list_tracks(url: str, kind: str, mix_limit: int = 50) -> list[Track]:
    """Fast listing via extract_flat. kind: 'video' | 'playlist' | 'mix'."""
    opts = {"skip_download": True}
    if kind == "video":
        url, opts["noplaylist"] = video_url(url), True
    else:
        opts["extract_flat"] = "in_playlist"
        if kind == "mix":
            opts["playlistend"] = mix_limit
    with _youtube(), _ydl(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") != "playlist":
        return [_track(info)]
    title = info.get("title") or info.get("id") or "playlist"
    # Entries without a usable id can't be downloaded or deduplicated: skip them.
    return [_track(e, title) for e in info.get("entries") or [] if isinstance(e, dict) and _entry_id(e)]


def download(
    track: Track,
    outdir: str | Path,
    quality: str = "192",
    subfolder: str = "",
    on_progress: Callable[[float, str], None] = lambda pct, phase: None,
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
            on_progress(d.get("downloaded_bytes", 0) / total * 100 if total else 0.0, "downloading")
        elif d.get("status") == "finished":
            on_progress(100.0, "downloading")

    def pp_hook(d):
        # ffmpeg conversion only reports started/finished: the UI shows it as indeterminate.
        phase = phase_for_postprocessor(d.get("postprocessor", ""))
        if phase and d.get("status") == "started":
            on_progress(0.0, phase)

    target = target_dir(outdir, subfolder)
    repair_archive(Path(outdir) / ARCHIVES[fmt])
    opts = {
        **format_opts(fmt, quality),
        "noplaylist": True,
        "outtmpl": str(target / f"%(title).{MAX_NAME_BYTES}B.%(ext)s"),  # .NB = truncate to N bytes
        "download_archive": str(Path(outdir) / ARCHIVES[fmt]),
        "progress_hooks": [hook],
        "postprocessor_hooks": [pp_hook],
    }
    # Each download extracts fresh: stream URLs from the listing were measured to fail with 403 when reused.
    with _youtube(), _ydl(opts) as ydl:
        if fmt == "audio":
            ydl.add_post_processor(ReliableThumbnail(), when="pre_process")
        info = ydl.extract_info(track.url, download=True)
    downloads = (info or {}).get("requested_downloads") or []
    if not downloads:
        return None  # skipped: already in download archive
    return downloads[0]["filepath"]


def repair_archive(archive: Path) -> Path | None:
    """If the download archive isn't valid UTF-8, keep a backup and rewrite it with its readable lines.

    yt-dlp fails to start with a corrupt archive, which would make every download fail.
    Returns the backup path, or None if nothing had to be done.
    """
    try:
        data = archive.read_bytes()
    except OSError:
        return None
    try:
        data.decode("utf-8")
        return None
    except UnicodeDecodeError:
        pass
    lines = [ln for ln in data.decode("utf-8", errors="replace").splitlines()
             if len(ln.split()) == 2 and "\ufffd" not in ln and "\x00" not in ln]
    backup = archive.with_name(f"{archive.name}.corrupt-{int(time.time())}")
    try:
        archive.replace(backup)
        archive.write_text("".join(f"{ln}\n" for ln in lines), "utf-8")
    except OSError:
        return None
    log.warning("Registro de descargas dañado: copia en %s, %d entradas recuperadas", backup, len(lines))
    return backup


MAX_NAME_BYTES = 150  # file/folder names: well under the 255-byte limit of common filesystems, short on Windows


def _trim_bytes(text: str, limit: int) -> str:
    return text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def target_dir(outdir: str | Path, subfolder: str) -> Path:
    """Folder for a download: `outdir`, or `outdir/<sanitized playlist title>`; never outside `outdir`."""
    base = Path(outdir)
    # Trailing dots/spaces are dropped (Windows strips them anyway), so "..." or ". ." can't collapse to "".
    name = _trim_bytes(sanitize_filename(subfolder or "").strip(), MAX_NAME_BYTES).rstrip(". ").strip()
    if name in ("", ".", ".."):
        return base
    target = base / name
    resolved_base = base.resolve()
    if target.resolve().parent != resolved_base:  # e.g. an existing symlink pointing elsewhere
        raise ValueError(f"La carpeta de destino queda fuera de {base}: {name}")
    return target


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
    with _youtube(), _ydl(opts) as ydl:
        ydl.download([video_url(url)])
    return path
