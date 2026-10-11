"""Fault-injection helpers. Everything here is offline and deterministic.

Tests marked `live` (real network/tools) are skipped unless PISTA_LIVE=1.
"""
import asyncio
import os

import pytest

from pista.core.models import Track
from pista.core.queue import BatchRunner, QueueModel

PAYLOAD = 'Song " innerHTML="<img src=x onerror=document.title=\'PWNED\'> \' < > & \\ / .. CON NUL'


def pytest_collection_modifyitems(config, items):
    if os.environ.get("PISTA_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live test: set PISTA_LIVE=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


def track(i, title=None, **kw) -> Track:
    vid = kw.pop("id", f"vid{i:08d}"[:11])
    return Track(vid, title or f"Pista {i}", "Canal", 100 + i, f"https://www.youtube.com/watch?v={vid}", None, **kw)


def model_with(n: int) -> QueueModel:
    m = QueueModel()
    m.add_tracks([track(i) for i in range(n)])
    return m


class Sleeps:
    """Fake asyncio.sleep: records requested delays and returns immediately."""

    def __init__(self):
        self.calls: list[float] = []

    async def __call__(self, seconds):
        self.calls.append(seconds)
        await asyncio.sleep(0)

    @property
    def total(self):
        return sum(self.calls)


def runner(model, download, **kw) -> BatchRunner:
    logs = []
    kw.setdefault("sleep", Sleeps())
    r = BatchRunner(model, download, out="/tmp/out", quality="192", fmt="audio",
                    log=lambda msg, level=0: logs.append((level, msg)), **kw)
    r.logs = logs
    return r


def run(coro):
    return asyncio.run(coro)
