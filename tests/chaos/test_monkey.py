"""Seeded random "monkey" over the queue/batch state machine, with injected failures.

Mirrors what the UI does (add, load, select, download, stop, retry, remove, clear) and checks the
invariants after every step. PISTA_MONKEY_STEPS / PISTA_MONKEY_SEED make longer or different runs.
"""
import asyncio
import os
import random

from yt_dlp.utils import DownloadError

from pista.core.batch import MAX_ATTEMPTS
from pista.core.breaker import Breaker
from pista.core.downloader import Cancelled
from pista.core.progress import PHASES
from pista.core.queue import STATES, BatchRunner, QueueModel, progress_total

from .conftest import track

STEPS = int(os.environ.get("PISTA_MONKEY_STEPS", "3000"))
SEED = int(os.environ.get("PISTA_MONKEY_SEED", "20261011"))


class Monkey:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.m = QueueModel()
        self.runner: BatchRunner | None = None
        self.task: asyncio.Task | None = None
        self.summaries = []
        self.batches = 0
        self.now = 0.0  # fake clock for the YouTube breaker; runner sleeps advance it
        self.breaker = Breaker(clock=lambda: self.now)

    async def sleep(self, seconds):
        self.now += seconds
        await asyncio.sleep(0)

    # --- fakes ---
    async def run_io(self, fn, *args):
        for _ in range(self.rng.randrange(4)):
            await asyncio.sleep(0)
        return fn(*args)

    def download(self, t, out, q, sub, on_progress, cancel, fmt):
        on_progress(self.rng.uniform(0, 100), "downloading")
        if self.rng.random() < 0.3:
            on_progress(0.0, self.rng.choice(["converting", "merging"]))
        roll = self.rng.random()
        if cancel.is_set() and roll < 0.8:
            raise Cancelled()
        if roll < 0.25:
            raise DownloadError(self.rng.choice(["ERROR: HTTP Error 403: Forbidden", "ERROR: timed out",
                                                 "ERROR: HTTP Error 429: Too Many Requests", "[Errno 28] No space"]))
        if roll < 0.35:
            raise OSError("disk went away")
        return None if roll < 0.6 else f"/out/{t.id}.mp3"  # nonexistent path → size 0

    # --- UI actions ---
    def active(self) -> bool:
        return self.task is not None and not self.task.done()

    def start(self):
        if self.active():
            return  # the UI's busy guard
        self._collect()
        self.runner = BatchRunner(self.m, self.download, out="/out", quality="192", fmt="audio",
                                  run_io=self.run_io, sleep=self.sleep, retry_delay=0.3, breaker=self.breaker)
        self.task = asyncio.ensure_future(self.runner.run())
        self.batches += 1

    def _collect(self):
        if self.task is not None and self.task.done():
            summary = self.task.result()  # re-raises if the batch crashed
            assert summary.done + summary.skipped + summary.failed + summary.stopped == len(self.runner.results)
            self.summaries.append(summary)
            self.task = None

    def step(self):
        r = self.rng
        ids = [t.id for t in self.m.tracks]
        action = r.choice(["add", "add", "toggle", "all", "remove", "clear", "download", "download",
                           "stop", "retry", "tick", "tick", "tick", "poll", "poll", "resume"])
        if action == "add":
            self.m.add_tracks([track(r.randrange(40)) for _ in range(r.randint(1, 3))], new=self.active())
        elif action == "toggle" and ids:
            self.m.toggle(r.choice(ids))
        elif action == "all":
            self.m.select_all(r.random() < 0.7)
        elif action == "remove" and ids:
            tid = r.choice(ids)
            if self.runner is not None and self.active():
                self.runner.cancel_item(tid)
            self.m.remove(tid)
        elif action == "clear":
            self.m.clear_finished(keep=self.runner.current if self.runner and self.active() else None)
        elif action == "download":
            self.start()
        elif action == "poll" and self.active() and self.runner.current:  # the UI timer
            self.m.set_state(self.runner.current, "running", self.runner.pct, phase=self.runner.phase)
        elif action == "resume":  # «Reanudar ahora»
            self.breaker.resume()
        elif action == "stop" and self.active():
            self.runner.stop()
        elif action == "retry":
            errs = [t for t in ids if self.m.state[t][0] == "error"]
            if errs:
                tid = r.choice(errs)
                if self.m.fails.get(tid, 0) >= MAX_ATTEMPTS:
                    self.m.fails[tid] = MAX_ATTEMPTS - 1
                self.m.checked[tid] = True
                self.m.set_state(tid, "queued")
                self.start()
        return action

    def check(self, where):
        m = self.m
        ids = [t.id for t in m.tracks]
        assert len(ids) == len(set(ids)), where
        assert set(m.state) == set(ids) == set(m.checked), where
        assert set(m.errors) <= set(ids) and set(m.fails) <= set(ids) and m.new <= set(ids), where
        assert all(s in STATES and 0 <= p <= 100 for s, p in m.state.values()), where
        assert all(1 <= f <= MAX_ATTEMPTS for f in m.fails.values()), (where, m.fails)
        running = [t for t in ids if m.state[t][0] == "running"]
        if self.active() and self.runner.paused:  # cooling down after a rate limit: nothing downloads
            assert running == [] and self.runner.current is None, where
        assert set(m.phase) == set(running), (where, m.phase, running)  # phase only for running rows
        assert all(p in PHASES for p in m.phase.values()), where
        assert len(running) <= 1, where
        if not self.active():
            assert running == [], f"{where}: row stuck in «running» with no batch"
        elif running:
            assert running == [self.runner.current], where
        assert sum(m.counts().values()) == len(ids), where
        assert 0 <= progress_total(m) <= 100, where


def test_monkey_state_machine():
    rng = random.Random(SEED)
    monkey = Monkey(rng)

    async def main():
        for n in range(STEPS):
            action = monkey.step()
            for _ in range(rng.randrange(3)):
                await asyncio.sleep(0)
            monkey._collect()
            monkey.check(f"step {n} ({action})")
        # drain: let the last batch finish
        if monkey.active():
            monkey.runner.stop()
        for _ in range(100_000):
            if not monkey.active():
                break
            await asyncio.sleep(0)
        assert not monkey.active(), "batch did not finish after Stop"
        monkey._collect()
        monkey.check("end")

    asyncio.run(main())
    assert monkey.batches > 10 and monkey.summaries  # the run exercised real batches
