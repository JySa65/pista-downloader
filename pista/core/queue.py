"""Download queue and batch state machine, independent of the UI (so it can be tested and fuzzed).

The UI's Queue subclasses QueueModel and repaints rows from the `_changed` / `_state_changed` hooks;
BatchRunner drives a batch over a QueueModel with an injected download function.
"""
import asyncio
import logging
import random
import threading
import time
import weakref
from collections import Counter
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .batch import MAX_ATTEMPTS, Result, Summary, friendly_error, human_size, is_rate_limited, strip_ansi, summarize
from .breaker import BREAKER, Breaker, CooldownActive
from .downloader import Cancelled
from .models import Track
from .progress import batch_status, item_progress, pace_status

# Random pause between downloads, as yt-dlp recommends to stay under YouTube's bot check.
PACE_MIN, PACE_MAX = 5, 10

STATES = ("queued", "running", "done", "skipped", "error", "stopped")
FINISHED = ("done", "skipped", "error", "stopped")


class QueueModel:
    """Rows and their state for the currently selected format (`fmt`).

    Completion is remembered per format in `done`, so an MP3 being downloaded never hides the MP4:
    switching the format re-evaluates every finished row.
    """

    def __init__(self, fmt: str = "audio") -> None:
        self.fmt = fmt
        self.done: dict[str, dict[str, tuple[str | None, int]]] = {}  # id -> fmt -> (path or None=archive, size)
        self.tracks: list[Track] = []
        self.checked: dict[str, bool] = {}
        self.state: dict[str, tuple[str, float]] = {}
        self.errors: dict[str, str] = {}
        self.fails: dict[str, int] = {}  # failed attempts per track
        self.sizes: dict[str, int] = {}
        self.new: set[str] = set()
        self.phase: dict[str, str] = {}  # only for «running» rows: downloading | converting | merging

    # --- hooks for the UI ---
    def _changed(self) -> None:
        """Rows were added/removed/re-checked."""

    def _state_changed(self, track_id: str) -> None:
        """One row's state/progress changed."""

    # --- operations ---
    def add_tracks(self, tracks: list[Track], new: bool = False) -> int:
        """Append tracks (deduplicated by video id), checked and queued; `new` marks them «Nuevo»."""
        added = [t for t in dict((t.id, t) for t in tracks).values() if t.id not in self.state]
        self.tracks += added
        for t in added:
            self.checked[t.id] = True
            self.state[t.id] = ("queued", 0.0)
            if new:
                self.new.add(t.id)
        if added:
            self._changed()
        return len(added)

    def next_pending(self) -> Track | None:
        """Next checked, queued track; re-read each time so tracks added mid-download are picked up."""
        return next((t for t in self.tracks if self.checked.get(t.id) and self.state[t.id][0] == "queued"), None)

    def clear_finished(self, keep: str | None) -> int:
        """Drop finished, failed, stopped and unchecked rows; never the one downloading (`keep`)."""
        drop = {t.id for t in self.tracks if t.id != keep and (
            not self.checked.get(t.id) or self.state[t.id][0] in FINISHED)}
        self._drop(drop)
        self._changed()
        return len(drop)

    def remove(self, track_id: str) -> Track | None:
        """Drop one row (the caller cancels it first if it is downloading)."""
        track = next((t for t in self.tracks if t.id == track_id), None)
        if track is None:
            return None
        self._drop({track_id})
        self._changed()
        return track

    def _drop(self, ids: set[str]) -> None:
        self.tracks = [t for t in self.tracks if t.id not in ids]
        for d in (self.checked, self.state, self.errors, self.fails, self.sizes, self.phase, self.done):
            for k in ids:
                d.pop(k, None)
        self.new -= ids

    def select_all(self, value: bool) -> None:
        self.checked = {t.id: value for t in self.tracks}
        self._changed()

    def toggle(self, track_id: str) -> None:
        if track_id in self.checked:
            self.checked[track_id] = not self.checked[track_id]
            self._changed()

    def selected(self) -> list[Track]:
        return [t for t in self.tracks if self.checked.get(t.id)]

    def set_state(self, track_id: str, state: str, pct: float = 0.0, phase: str | None = None) -> None:
        if state not in STATES:
            raise ValueError(f"unknown state: {state}")
        if track_id not in self.state:
            return  # removed meanwhile
        self.state[track_id] = (state, pct)
        if state == "running":
            self.phase[track_id] = phase or self.phase.get(track_id) or "downloading"
        else:
            self.phase.pop(track_id, None)
        self._state_changed(track_id)

    def mark_done(self, track_id: str, fmt: str, path: str | None, size: int = 0) -> None:
        """A finished download (path) or an archive skip (path None) for one format."""
        if track_id not in self.state:
            return
        self.done.setdefault(track_id, {})[fmt] = (path, size)
        if fmt == self.fmt:
            if size:
                self.sizes[track_id] = size
            self.set_state(track_id, "done" if path else "skipped")

    def other_formats(self, track_id: str) -> list[str]:
        """Formats this row is already downloaded in, other than the selected one (for «Ya en MP3»)."""
        return [f for f in self.done.get(track_id, {}) if f != self.fmt]

    def set_format(self, fmt: str) -> None:
        """Re-evaluate finished rows for the newly selected format (errors/stops are left as they are)."""
        self.fmt = fmt
        for tid, (state, _) in list(self.state.items()):
            mine = self.done.get(tid, {}).get(fmt)
            if mine is not None:
                path, size = mine
                if size:
                    self.sizes[tid] = size
                else:
                    self.sizes.pop(tid, None)
                if state in ("queued", "done", "skipped"):
                    self.state[tid] = ("done" if path else "skipped", 0.0)
            else:
                self.sizes.pop(tid, None)
                if state in ("done", "skipped"):
                    self.state[tid] = ("queued", 0.0)
        self._changed()

    def title(self, track_id: str) -> str:
        return next((t.title for t in self.tracks if t.id == track_id), track_id)

    def counts(self) -> Counter:
        return Counter(s for s, _ in self.state.values())


def progress_total(model: QueueModel) -> float:
    sel = [t.id for t in model.selected()]
    if not sel:
        return 0.0
    return sum(item_progress(model.state[i][0], model.phase.get(i), model.state[i][1]) for i in sel) / len(sel)


class _Either:
    """What download() polls: the batch's Detener or the current row's «×»."""

    def __init__(self, *events: threading.Event) -> None:
        self.events = events

    def is_set(self) -> bool:
        return any(e.is_set() for e in self.events)


RunIO = Callable[..., Awaitable[Any]]
log = logging.getLogger("pista")
_ACTIVE: "weakref.WeakSet[BatchRunner]" = weakref.WeakSet()


def stop_all() -> None:
    """Stop every running batch (app shutdown)."""
    for r in list(_ACTIVE):
        r.stop()


async def _direct(fn, *args):
    return fn(*args)


class BatchRunner:
    """One download batch over a QueueModel. Not reentrant: create one per batch."""

    def __init__(self, model: QueueModel, download: Callable, *, out: str, quality: str, fmt: str,
                 run_io: RunIO = _direct, sleep: Callable[[float], Awaitable] = asyncio.sleep,
                 retry_delay: float = 10, log: Callable[[str, int], None] = lambda m, lvl=logging.INFO: None,
                 status: Callable[[str], None] = lambda text: None, fmt_text: str = "",
                 on_progress: Callable[[], None] = lambda: None, stop_grace: float = 10.0,
                 breaker: Breaker = BREAKER, pace: tuple[float, float] = (PACE_MIN, PACE_MAX)) -> None:
        self.model, self.download = model, download
        self.out, self.quality, self.fmt, self.fmt_text = out, quality, fmt, fmt_text
        self.run_io, self.sleep, self.retry_delay = run_io, sleep, retry_delay
        self._log, self._status, self._on_progress = log, status, on_progress
        self.stop_grace = stop_grace  # how long to wait for a download that ignores Stop (hung ffmpeg)
        self._abandoned: set[asyncio.Task] = set()
        self.cancel = threading.Event()
        self.item_cancel = threading.Event()
        self.current: str | None = None
        self.pct = 0.0  # written by the download thread, read by the UI timer
        self.phase = "downloading"  # idem
        self.position = (0, 0)  # (n, total) for «Descargando n de total»
        self.results: dict[str, Result] = {}
        self.breaker = breaker
        self.paused = False  # waiting for the YouTube cooldown
        self.pace = pace  # (min, max) seconds between downloads
        self._pace_due = False  # no pause before the first download of the run

    # --- UI callbacks: a broken one (e.g. window closed) must never abort the batch ---
    def log(self, msg: str, level: int = logging.INFO) -> None:
        try:
            self._log(msg, level)
        except Exception:
            log.log(level, msg)

    def status(self, text: str) -> None:
        try:
            self._status(text)
        except Exception:
            log.debug("status callback failed", exc_info=True)

    def on_progress(self) -> None:
        try:
            self._on_progress()
        except Exception:
            log.debug("progress callback failed", exc_info=True)

    # --- controls ---
    def stop(self) -> None:
        self.cancel.set()

    def cancel_item(self, track_id: str) -> None:
        if self.current == track_id:
            self.item_cancel.set()

    # --- the batch ---
    async def run(self) -> Summary:
        _ACTIVE.add(self)
        try:
            return await self._run()
        finally:
            _ACTIVE.discard(self)

    async def _run(self) -> Summary:
        started = time.monotonic()
        m = self.model
        for t in m.selected():  # re-run anything selected that was stopped
            if m.state[t.id][0] == "stopped":
                m.set_state(t.id, "queued")
        self.log(f"▶ Descargando en {self.out} · {self.fmt_text}", logging.INFO)
        await self._run_pending()
        # One automatic second pass for items that failed only once.
        again = [tid for tid, r in self.results.items() if r.state == "error" and m.fails.get(tid) == 1]
        if again and not self.cancel.is_set():
            self.status(f"Reintentando {len(again)} fallida(s) en {self.retry_delay:g} s…")
            for tid in again:
                m.set_state(tid, "queued")  # shows «Reintentando (2/3)»
            self.log(f"↻ Reintentando {len(again)} fallida(s) en {self.retry_delay:g} s", logging.WARNING)
            await self._cooldown()  # the auto-retry never fires during a cooldown
            await self._wait(self.retry_delay, step=0.1)
            self._pace_due = False  # the retry delay already was the pause
            await self._run_pending()

        stopped = self.cancel.is_set()
        if stopped:
            for t in m.selected():  # anything left in the queue counts as stopped
                if m.state[t.id][0] == "queued":
                    m.set_state(t.id, "stopped")
                    self.results.setdefault(t.id, Result(t.title, "stopped"))
            self.log("Detenido por el usuario.", logging.INFO)
        self.status("Detenido." if stopped else "Terminado.")
        return summarize(list(self.results.values()), time.monotonic() - started,
                         ended_at=time.strftime("%H:%M"), processed=len(self.results))

    async def _wait(self, seconds: float, step: float = 1.0) -> None:
        """Sleep in small steps so Stop interrupts the wait."""
        left = seconds
        while left > 0 and not self.cancel.is_set():
            await self.sleep(min(step, left))
            left -= step

    async def _download(self, t: Track, on_progress):
        """Run one download; if it ignores Stop/«×» for `stop_grace` seconds, abandon it and raise Cancelled.

        A stuck item (e.g. ffmpeg hanging during conversion never calls the progress hook again) would
        otherwise keep the whole batch, and the UI, busy forever.
        """
        task = asyncio.ensure_future(self.run_io(self.download, t, self.out, self.quality, t.playlist,
                                                 on_progress, _Either(self.cancel, self.item_cancel), self.fmt))
        asked = None
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.25)
            if done:
                return task.result()
            if self.cancel.is_set() or self.item_cancel.is_set():
                asked = asked or time.monotonic()
                if time.monotonic() - asked >= self.stop_grace:
                    self._abandoned.add(task)  # keep a reference; its late result is ignored
                    task.add_done_callback(lambda f: (self._abandoned.discard(f), f.cancelled() or f.exception()))
                    self.log(f"⚠ {t.title} — no respondió al detener; se abandonó", logging.WARNING)
                    raise Cancelled()

    async def _cooldown(self) -> None:
        """While YouTube is rate-limiting us, pause everything (items stay queued). Stop or
        «Reanudar ahora» (breaker.resume) end the wait."""
        if not self.breaker.is_open() or self.cancel.is_set():
            return
        self.paused = True
        self._pace_due = False  # the cooldown already is the pause
        self.log(self.breaker.message(), logging.WARNING)
        try:
            while self.breaker.is_open() and not self.cancel.is_set():
                self.status(self.breaker.message())
                await self.sleep(min(1.0, self.breaker.remaining()))
        finally:
            self.paused = False

    async def _pause(self) -> None:
        """Random pause between downloads, counted down on the status line (Stop interrupts it).

        Runs while `current` is None, so the UI timer doesn't overwrite the status line."""
        left = round(random.uniform(*self.pace))
        self.log(pace_status(left), logging.INFO)
        while left > 0 and not self.cancel.is_set():
            self.status(pace_status(left))
            await self.sleep(1)
            left -= 1

    async def _run_pending(self) -> None:
        m = self.model
        while True:
            await self._cooldown()
            if self.cancel.is_set() or (t := m.next_pending()) is None:
                break
            if self._pace_due:
                self._pace_due = False
                await self._pause()
                continue  # re-check the cooldown, Stop and the next track after the pause
            self._pace_due = True
            attempt = m.fails.get(t.id, 0) + 1
            done = sum(r.state != "error" for r in self.results.values())
            pending = sum(1 for x in m.selected() if m.state[x.id][0] == "queued")
            self.position = (done + 1, done + pending)
            self.status(batch_status("downloading", *self.position, self.fmt_text))
            self.log(f"… {t.title} — descargando" + (f" (intento {attempt}/{MAX_ATTEMPTS})" if attempt > 1 else ""),
                     logging.INFO)
            self.current, self.pct, self.phase = t.id, 0.0, "downloading"
            self.item_cancel.clear()
            m.set_state(t.id, "running", 0.0, phase="downloading")

            def on_progress(pct: float, phase: str = "downloading") -> None:
                self.pct, self.phase = min(max(pct, 0.0), 100.0), phase

            try:
                path = await self._download(t, on_progress)
                size = Path(path).stat().st_size if path and Path(path).exists() else 0
                if t.id not in m.state:  # removed right as it finished
                    continue
                self.results[t.id] = Result(t.title, "done" if path else "skipped", path, size)
                m.mark_done(t.id, self.fmt, path, size)
                self.log(f"✓ {path} ({human_size(size)})" if path else f"= {t.title} — ya estaba, se omite",
                         logging.INFO)
            except CooldownActive:  # another activity tripped the breaker: wait, then retry this item
                m.set_state(t.id, "queued")
            except Cancelled:
                if t.id in m.state:  # stopped batch; a removed row is just dropped
                    self.results[t.id] = Result(t.title, "stopped")
                    m.set_state(t.id, "stopped", self.pct)
            except Exception as e:
                if t.id not in m.state:  # removed while downloading
                    continue
                if is_rate_limited(str(e)):  # not the item's fault: pause everything, keep it queued
                    self.breaker.trip()
                    m.set_state(t.id, "queued")
                    self.log(f"↻ {t.title} — {friendly_error(str(e))}", logging.WARNING)
                    continue
                m.fails[t.id] = attempt
                self.results[t.id] = Result(t.title, "error", error=strip_ansi(str(e)))
                m.errors[t.id] = friendly_error(str(e))
                m.set_state(t.id, "error")
                self.log(f"✗ {t.title} (intento {attempt}/{MAX_ATTEMPTS}) — {strip_ansi(str(e))}", logging.ERROR)
            finally:
                self.current = None  # before any pause: the UI timer must not repaint this row as running
                self.on_progress()
