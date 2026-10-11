"""What «Descargar seleccionadas» will do: pending items, estimated size/duration and notes."""
from dataclasses import dataclass, field
from pathlib import Path

from .models import Track

# Typical YouTube MP4 (H.264 + AAC) total bitrate per height cap, bits/s; used when yt-dlp gave no size.
VIDEO_BITRATE = {"360p": 700_000, "480p": 1_200_000, "720p": 2_500_000, "1080p": 4_500_000, "4K": 16_000_000}
HEIGHT = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080, "4K": 2160}
PENDING_STATES = ("queued", "stopped")


def _size(f: dict) -> int:
    return f.get("filesize") or f.get("filesize_approx") or 0


def video_sizes(formats: list[dict]) -> dict[str, int]:
    """Bytes per resolution label, mirroring format_opts: best mp4 video <= cap + best m4a audio."""
    audio = max((_size(f) for f in formats if f.get("vcodec") == "none" and f.get("ext") == "m4a"), default=0)
    videos = [f for f in formats if f.get("acodec") == "none" and f.get("ext") == "mp4" and f.get("height") and _size(f)]
    out = {}
    for label, cap in HEIGHT.items():
        fit = [f for f in videos if f["height"] <= cap]
        if fit:
            out[label] = _size(max(fit, key=lambda f: (f["height"], _size(f)))) + audio
    return out


def estimate_bytes(track: Track, fmt: str, quality: str) -> int:
    if fmt == "video" and track.video_sizes.get(quality):
        return track.video_sizes[quality]
    if not track.duration:
        return 0
    bps = int(quality) * 1000 if fmt == "audio" else VIDEO_BITRATE[quality]
    return int(track.duration) * bps // 8


def archived_ids(archive: str | Path) -> set[str]:
    """Video ids in a yt-dlp download archive ('youtube <id>' per line)."""
    try:
        lines = Path(archive).read_text("utf-8", errors="replace").splitlines()  # tolerate a corrupt file
    except OSError:
        return set()
    return {parts[1] for parts in (line.split() for line in lines) if len(parts) == 2}


@dataclass
class Plan:
    count: int
    pending: list[str]
    skip: list[str]  # selected but already in the archive: marked «Ya estaba» without downloading
    format_label: str
    size_bytes: int
    duration: int
    notes: list[tuple[str, str]] = field(default_factory=list)  # (kind: plain|err|info|warn, text)
    can_start: bool = False  # pending items AND the user confirmed they have the right to download them


def plan_download(items: list[tuple[Track, str, bool]], fmt: str, quality: str,
                  archived: set[str], running: bool, consent: bool = False) -> Plan:
    """items: (track, state, checked) in queue order."""
    selected = [(t, s) for t, s, checked in items if checked]
    pending = [t for t, s in selected if s in PENDING_STATES and t.id not in archived]
    skip = [t.id for t, s in selected if s in PENDING_STATES and t.id in archived]
    had = len(skip) + sum(s in ("done", "skipped") for _, s in selected)
    failed = sum(s == "error" for _, s in selected)
    notes = []
    if had:
        notes.append(("plain", f"{had} ya están en la carpeta y se omitirán."))
    if failed:
        notes.append(("err", f"{failed} fallida(s) no se incluyen. Usa «Reintentar» en su fila."))
    if running:
        notes.append(("info", "Ya hay una descarga en curso; estas se añaden a la misma cola."))
    if not pending:
        notes.append(("warn", "No hay pistas pendientes seleccionadas."))
    return Plan(
        count=len(pending),
        pending=[t.id for t in pending],
        skip=skip,
        format_label=f"Audio · MP3 {quality} kbps" if fmt == "audio" else f"Video · MP4 {quality}",
        size_bytes=sum(estimate_bytes(t, fmt, quality) for t in pending),
        duration=sum(int(t.duration or 0) for t in pending),
        notes=notes,
        can_start=bool(pending) and consent,
    )
