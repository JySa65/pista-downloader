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


_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    """Remove terminal color codes (yt-dlp may add them to error messages)."""
    return _ANSI.sub("", text or "")


# (pattern, friendly reason) — checked in order; the first match wins.
BOT_HINT = "Puedes activar «Usar la sesión de YouTube de mi navegador» en las opciones."

_REASONS = [
    # Optional browser-session cookies (cookiesfrombrowser) — known platform limits.
    (r"Failed to decrypt with DPAPI|app.?bound encryption",
     "No se pudieron leer las cookies de ese navegador en Windows (los navegadores basados en Chrome las cifran). "
     "Prueba con Firefox."),
    (r"Could not copy .* cookie database|database is locked",
     "El navegador tiene sus cookies bloqueadas: ciérralo del todo e inténtalo de nuevo."),
    (r"Cookies\.binarycookies|could not find safari cookies",
     "Para usar Safari, da a Pista «Acceso total al disco» en Ajustes del Sistema → Privacidad y seguridad, "
     "o elige otro navegador."),
    (r"could not find \w+ cookies database|could not find local state file",
     "No se encontró el perfil de ese navegador. ¿Está instalado y has iniciado sesión en YouTube con él?"),
    (r"failed to load cookies|cannot decrypt .* cookies|failed to read from keyring",
     "No se pudieron leer las cookies del navegador. Si el sistema pidió permiso (llavero), acéptalo, "
     "o desactiva la opción."),
    (r"confirm you.?re not a bot", "YouTube pide verificar que no eres un robot. Espera unos minutos e inténtalo de nuevo. "
                                   + BOT_HINT),
    (r"HTTP Error 429|Too Many Requests", "YouTube está limitando las descargas (demasiadas solicitudes). "
                                          "Espera unos minutos e inténtalo de nuevo."),
    (r"Private video", "El video es privado."),
    (r"members.only|Join this channel", "El video es solo para miembros del canal."),
    (r"confirm your age|age.restricted|inappropriate for some users", "El video tiene restricción de edad."),
    (r"not (made this video )?available in your country|blocked it in your country|geo.?restrict",
     "El video no está disponible en tu país."),
    (r"Video unavailable|This video (is|has been) (no longer available|removed)|has been terminated",
     "El video no está disponible."),
    (r"nodename nor servname|Name or service not known|getaddrinfo failed|Temporary failure in name resolution|"
     r"timed out|Network is unreachable|Connection (refused|reset)|No route to host|urlopen error",
     "Sin conexión o no se encontró el servidor. Revisa tu internet."),
]


def friendly_error(msg: str, limit: int = 120) -> str:
    """Short Spanish reason for a yt-dlp error; unknown errors fall back to the cleaned-up message."""
    clean = strip_ansi(msg)
    for pattern, reason in _REASONS:
        if re.search(pattern, clean, re.IGNORECASE):
            return reason
    return short_error(clean, limit)


def short_error(msg: str, limit: int = 120) -> str:
    """One readable line from a yt-dlp error: no 'ERROR:' / '[extractor] id:' prefixes."""
    msg = strip_ansi(msg)
    line = msg.strip().splitlines()[0] if msg.strip() else ""
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
        failures=[(r.title, friendly_error(r.error)) for r in results if r.state == "error"],
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


_RATE_LIMIT = re.compile(r"HTTP Error 429|Too Many Requests|confirm you.?re not a bot|rate.?limit", re.IGNORECASE)


def is_rate_limited(message: str) -> bool:
    """YouTube is throttling us: keep going, but slowly."""
    return bool(_RATE_LIMIT.search(message or ""))


def backoff(n: int, base: float = 15.0, cap: float = 300.0) -> float:
    """Seconds to wait after the n-th rate-limited item in a row (n >= 1): 15, 30, 60, … up to 5 min."""
    return min(cap, base * 2 ** (n - 1))
