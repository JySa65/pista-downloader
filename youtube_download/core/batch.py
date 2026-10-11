"""Per-item download results and the end-of-batch summary."""
import re
from dataclasses import dataclass, field


@dataclass
class Result:
    title: str
    state: str  # done | skipped | error | stopped
    path: str | None = None
    size: int = 0
    error: str = ""


@dataclass
class Summary:
    done: int
    skipped: int
    failed: int
    stopped: int
    total_bytes: int
    elapsed: float
    failures: list[tuple[str, str]] = field(default_factory=list)  # (title, short reason)
    first_new: str | None = None  # first newly downloaded file, for "Ir al reproductor"
    ended_at: str = ""  # HH:MM
    subtitle: str = ""


def short_error(msg: str, limit: int = 120) -> str:
    """One readable line from a yt-dlp error: no 'ERROR:' / '[extractor] id:' prefixes."""
    line = (msg or "").strip().splitlines()[0] if (msg or "").strip() else ""
    line = re.sub(r"^(ERROR:\s*)?(\[[\w:]+\]\s*[\w-]+:\s*)?", "", line).strip()
    if not line:
        return "Error desconocido"
    return line if len(line) <= limit else line[: limit - 1] + "…"


def summarize(results: list[Result], elapsed: float, ended_at: str = "", processed: int | None = None) -> Summary:
    count = lambda state: sum(r.state == state for r in results)  # noqa: E731
    n = len(results) if processed is None else processed
    subtitle = (f"Se detuvo a las {ended_at}. Las pendientes quedaron como «Detenida»; "
                "puedes reanudarlas con «Descargar seleccionadas».") if count("stopped") \
        else f"Finalizó a las {ended_at} · {n} pistas procesadas"
    return Summary(
        done=count("done"),
        skipped=count("skipped"),
        failed=count("error"),
        stopped=count("stopped"),
        total_bytes=sum(r.size for r in results if r.state == "done"),
        elapsed=elapsed,
        failures=[(r.title, short_error(r.error)) for r in results if r.state == "error"],
        first_new=next((r.path for r in results if r.state == "done" and r.path), None),
        ended_at=ended_at,
        subtitle=subtitle,
    )


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def human_time(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60} s"
    return f"{s // 3600} h {s % 3600 // 60} min"


MAX_ATTEMPTS = 3  # first try + automatic retry + one manual "Reintentar"
_LABELS = {"queued": "En cola", "done": "Listo", "skipped": "Ya estaba", "error": "Error", "stopped": "Detenida"}


def status_label(state: str, pct: float, failed_attempts: int) -> str:
    """Queue status chip text; a re-queued failure shows which attempt is next."""
    if state == "running":
        return f"{pct:.0f}%"
    if state == "queued" and failed_attempts:
        return f"Reintentando ({failed_attempts + 1}/{MAX_ATTEMPTS})"
    return _LABELS[state]
