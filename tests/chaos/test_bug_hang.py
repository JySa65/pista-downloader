"""8/10/11/12: a download that ignores Stop (hung ffmpeg) or a broken UI callback must not freeze the batch."""
import asyncio
import threading

import pytest

from pista.core.queue import BatchRunner, stop_all

from .conftest import model_with


def hanging(release: threading.Event):
    def download(t, out, q, sub, on_progress, cancel, fmt):
        release.wait(30)  # e.g. ffmpeg stuck in post-processing: the progress hook is never called again
        return None
    return download


async def to_thread(fn, *args):
    return await asyncio.to_thread(fn, *args)


def test_stop_returns_even_if_the_download_never_checks_cancel():
    release = threading.Event()
    m = model_with(3)
    r = BatchRunner(m, hanging(release), out="/o", quality="192", fmt="audio", run_io=to_thread, stop_grace=0.3)

    async def main():
        task = asyncio.ensure_future(r.run())
        await asyncio.sleep(0.2)
        r.stop()
        try:
            return await asyncio.wait_for(task, 5)
        finally:
            release.set()  # let the abandoned worker thread end so asyncio.run can shut down

    try:
        summary = asyncio.run(main())
    finally:
        release.set()
    assert summary.stopped == 3
    assert [m.state[t.id][0] for t in m.tracks] == ["stopped"] * 3  # nothing left «running»


def test_removing_a_hung_item_moves_on_to_the_next():
    release = threading.Event()
    m = model_with(2)
    calls = []

    def download(t, *a):
        calls.append(t.id)
        if t.id == "vid00000000":
            release.wait(30)
        return None

    r = BatchRunner(m, download, out="/o", quality="192", fmt="audio", run_io=to_thread, stop_grace=0.3, pace=(0, 0))

    async def main():
        task = asyncio.ensure_future(r.run())
        await asyncio.sleep(0.2)
        r.cancel_item("vid00000000")
        m.remove("vid00000000")
        try:
            return await asyncio.wait_for(task, 5)
        finally:
            release.set()

    try:
        summary = asyncio.run(main())
    finally:
        release.set()
    assert calls == ["vid00000000", "vid00000001"] and summary.skipped == 1


def test_stop_all_on_app_shutdown():
    release = threading.Event()
    m = model_with(2)
    r = BatchRunner(m, hanging(release), out="/o", quality="192", fmt="audio", run_io=to_thread, stop_grace=0.3)

    async def main():
        task = asyncio.ensure_future(r.run())
        await asyncio.sleep(0.2)
        stop_all()
        try:
            return await asyncio.wait_for(task, 5)
        finally:
            release.set()

    try:
        assert asyncio.run(main()).stopped == 2
    finally:
        release.set()


def test_broken_ui_callbacks_do_not_abort_the_batch():
    def boom(*a, **k):
        raise RuntimeError("element was deleted (window closed)")

    m = model_with(2)
    r = BatchRunner(m, lambda *a: None, out="/o", quality="192", fmt="audio", status=boom, log=boom, on_progress=boom,
                    pace=(0, 0))
    summary = asyncio.run(asyncio.wait_for(r.run(), 5))
    assert summary.skipped == 2
