"""Download phases and how they map to progress bars and labels.

yt-dlp reports real byte progress while downloading. Conversion (ffmpeg via yt-dlp post-processors)
only reports started/finished, so that phase is shown as indeterminate, never as a made-up percentage.
"""
from .batch import status_label

PHASES = ("downloading", "converting", "merging")
DOWNLOAD_WEIGHT = 85  # share of an item's progress bar for the download; the rest is conversion

_PP_PHASE = {
    "ExtractAudio": "converting",
    "Metadata": "converting",
    "EmbedThumbnail": "converting",
    "Merger": "merging",
}


def phase_for_postprocessor(key: str) -> str | None:
    """Phase for a yt-dlp post-processor key; None for ones that don't change what the user sees
    (e.g. ThumbnailsConvertor runs before the download starts)."""
    return _PP_PHASE.get(key)


def item_progress(state: str, phase: str | None, pct: float) -> float:
    """0–100 for one item, weighting download vs conversion so the bar never jumps from ~95 to 100."""
    if state in ("done", "skipped", "error"):
        return 100.0
    if state == "running" and phase in ("converting", "merging"):
        return float(DOWNLOAD_WEIGHT)
    if state in ("running", "stopped"):
        return DOWNLOAD_WEIGHT * min(max(pct, 0.0), 100.0) / 100
    return 0.0


def row_label(state: str, pct: float, failed_attempts: int, phase: str | None) -> str:
    if state == "running":
        if phase == "converting":
            return "Convirtiendo…"
        if phase == "merging":
            return "Uniendo…"
        return f"Descargando {pct:.0f}%"
    return status_label(state, pct, failed_attempts)


def batch_status(phase: str | None, position: int, total: int, fmt_text: str) -> str:
    if phase == "converting":
        return f"Convirtiendo {position} de {total}…"
    if phase == "merging":
        return f"Uniendo audio y video {position} de {total}…"
    return f"Descargando {position} de {total} · {fmt_text}"


def pace_status(seconds: int) -> str:
    return (f"Pausa de {seconds} s antes de la siguiente canción para que YouTube no pida verificar "
            "que no eres un robot…")
