"""Load pasted links into tracks: Mix choice, per-link errors, backoff, and the message shown to the user."""
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .batch import friendly_error, is_rate_limited, strip_ansi
from .breaker import BREAKER, Breaker
from .models import Track
from .urls import classify


@dataclass
class LoadOutcome:
    url: str
    kind: str
    tracks: list[Track] = field(default_factory=list)
    error: str | None = None  # friendly reason shown next to the link
    raw: str | None = None  # full error for the log file
    skipped: bool = False  # the user closed the Mix dialog


async def _direct(fn, *args):
    return fn(*args)


async def load_links(urls: list[str], list_tracks: Callable, *, limit: int,
                     choose_mix: Callable[[str], Awaitable[str | None]],
                     run_io: Callable = _direct, sleep: Callable = asyncio.sleep,
                     breaker: Breaker = BREAKER) -> list[LoadOutcome]:
    outcomes = []
    for url in urls:
        kind = classify(url)
        if kind == "mix":
            kind = await choose_mix(url)
            if kind is None:
                outcomes.append(LoadOutcome(url, "mix", skipped=True))
                continue
        if breaker.is_open():  # YouTube is rate-limiting: don't send more requests; keep the link for later
            outcomes.append(LoadOutcome(url, kind, error=breaker.message(), raw=breaker.message()))
            continue
        try:
            tracks = list(await run_io(list_tracks, url, kind, limit) or [])
        except Exception as e:
            raw = strip_ansi(str(e))
            outcomes.append(LoadOutcome(url, kind, error=friendly_error(raw), raw=raw))
            if is_rate_limited(raw):
                breaker.trip()  # pause ALL YouTube activity (also done by list_tracks itself)
            continue
        if not tracks:
            outcomes.append(LoadOutcome(url, kind, error="El link no tiene pistas disponibles."))
        else:
            outcomes.append(LoadOutcome(url, kind, tracks=tracks))
    return outcomes


def load_message(outcomes: list[LoadOutcome], added: int) -> tuple[str, str]:
    """(text, kind: ok|info|warning|error) for the notification and the log line. Never a bare «0 añadidas»."""
    failed = [o for o in outcomes if o.error]
    found = sum(len(o.tracks) for o in outcomes)
    parts = []
    if added:
        parts.append(f"{added} pista(s) añadidas" + ("" if failed else " al final de la cola"))
    elif found:
        parts.append("La pista ya estaba en la cola" if found == 1 else f"Las {found} pistas ya estaban en la cola")
    if failed:
        reason = failed[0].error if len({o.error for o in failed}) == 1 else "varios motivos (ver el registro)"
        parts.append(f"{len(failed)} link{'s' if len(failed) > 1 else ''} no se "
                     f"{'pudieron' if len(failed) > 1 else 'pudo'} cargar: {reason}")
    if not parts:
        return ("No se cargó nada.", "info")
    text = " · ".join(parts)
    text = text if text.endswith((".", "…")) else text + "."
    kind = "error" if failed and not added else "warning" if failed else "ok" if added else "info"
    return (text, kind)
