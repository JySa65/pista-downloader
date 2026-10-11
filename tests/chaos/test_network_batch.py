"""1/2/10: failures, retries and Stop inside a batch (fake downloads, no network)."""
import errno
import logging
import socket

from yt_dlp.utils import DownloadError

from pista.core.downloader import Cancelled
from pista.core.queue import BatchRunner, QueueModel

from .conftest import PAYLOAD, Sleeps, model_with, run, runner, track


def test_connection_drop_mid_download_marks_error_retries_and_continues():
    calls = []

    def download(t, out, q, sub, on_progress, cancel, fmt):
        calls.append(t.id)
        if t.id == "vid00000000" and calls.count(t.id) == 1:
            on_progress(37.0, "")
            raise DownloadError("ERROR: [download] Got error: The read operation timed out")
        return None  # "already there" for the others

    m = model_with(3)
    r = runner(m, download, retry_delay=10)
    summary = run(r.run())
    first = "vid00000000"
    assert calls == [first, "vid00000001", "vid00000002", first]  # batch continued, then one auto-retry
    assert m.state[first][0] == "skipped" and m.fails[first] == 1
    assert summary.failed == 0 and summary.skipped == 3
    assert any("intento 2/3" in msg for _, msg in r.logs)
    assert r.sleep.total >= 10 * 0.99  # waited the retry delay, didn't hammer


def test_permanent_failure_stops_after_retry_with_short_reason():
    def download(*a):
        raise DownloadError("ERROR: [youtube] vid00000000: unable to download video data: HTTP Error 403: Forbidden")

    m = model_with(1)
    summary = run(runner(m, download).run())
    t = "vid00000000"
    assert m.state[t][0] == "error" and m.fails[t] == 2
    assert m.errors[t] == "unable to download video data: HTTP Error 403: Forbidden"
    assert summary.failed == 1 and summary.failures[0][1].endswith("HTTP Error 403: Forbidden")


def test_5xx_dns_disk_full_and_deleted_folder_are_item_errors_not_crashes():
    errors = {
        "vid00000000": DownloadError("ERROR: unable to download webpage: HTTP Error 503: Service Unavailable"),
        "vid00000001": DownloadError("ERROR: [Errno 8] nodename nor servname provided, or not known"),
        "vid00000002": OSError(errno.ENOSPC, "No space left on device"),
        "vid00000003": FileNotFoundError(errno.ENOENT, "No such file or directory", "/gone/out"),
        "vid00000004": PermissionError(errno.EACCES, "Permission denied", "/readonly"),
        "vid00000005": socket.timeout("timed out"),
    }

    def download(t, *a):
        raise errors[t.id]

    m = model_with(6)
    summary = run(runner(m, download).run())
    assert summary.failed == 6
    assert all(m.state[t][0] == "error" and m.errors[t] for t in errors)
    assert "No space left on device" in m.errors["vid00000002"]


def test_stop_during_download_marks_current_and_rest_stopped_and_resumes():
    def download(t, out, q, sub, on_progress, cancel, fmt):
        if cancel.is_set():
            raise Cancelled()
        return None

    m = model_with(3)
    r = runner(m, download)
    r.stop()
    summary = run(r.run())
    assert {s for s, _ in m.state.values()} == {"stopped"} and summary.stopped == 3
    again = runner(m, lambda *a: None)
    summary2 = run(again.run())
    assert summary2.skipped == 3 and {s for s, _ in m.state.values()} == {"skipped"}


def test_stop_during_retry_delay_skips_the_retry_pass():
    calls = []

    def download(t, *a):
        calls.append(t.id)
        raise DownloadError("ERROR: boom")

    m = model_with(1)
    sleeps = Sleeps()
    r = runner(m, download, sleep=sleeps, retry_delay=10)

    async def stop_on_first_sleep(seconds):
        r.stop()
        await sleeps(seconds)

    r.sleep = stop_on_first_sleep
    summary = run(r.run())
    assert calls == ["vid00000000"]  # no second attempt after Stop
    # The row is resumable («Detenida»); the summary still reports the attempt that failed.
    assert m.state["vid00000000"][0] == "stopped" and summary.failed == 1


def test_remove_downloading_item_during_conversion_drops_it_without_crash():
    m = model_with(2)
    r = runner(m, None)

    def download(t, out, q, sub, on_progress, cancel, fmt):
        if t.id == "vid00000000":
            r.cancel_item(t.id)  # «×» pressed while ffmpeg converts: the hook is no longer called
            m.remove(t.id)
            return "/tmp/out/a.mp3"  # conversion finishes anyway
        return None

    r.download = download
    summary = run(r.run())
    assert "vid00000000" not in m.state and "vid00000000" not in r.results
    assert m.state["vid00000001"][0] == "skipped" and summary.skipped == 1


def test_payload_titles_and_errors_flow_through_as_plain_strings():
    def download(t, *a):
        raise DownloadError(f"ERROR: [youtube] x: {PAYLOAD}")

    m = QueueModel()
    m.add_tracks([track(0, title=PAYLOAD)])
    r = runner(m, download)
    summary = run(r.run())
    assert summary.failures[0][0] == PAYLOAD
    assert PAYLOAD in m.errors["vid00000000"] or m.errors["vid00000000"].startswith("Song")
    assert any(level == logging.ERROR and PAYLOAD in msg for level, msg in r.logs)


def test_two_runners_never_download_the_same_item():
    seen = []

    m = model_with(10)

    async def interleave(fn, *args):
        import asyncio
        await asyncio.sleep(0)
        return fn(*args)

    def download(t, *a):
        seen.append(t.id)
        return None

    async def both():
        import asyncio
        a = BatchRunner(m, download, out="/o", quality="192", fmt="audio", run_io=interleave)
        b = BatchRunner(m, download, out="/o", quality="192", fmt="audio", run_io=interleave)
        await asyncio.gather(a.run(), b.run())

    run(both())
    assert sorted(seen) == sorted(t.id for t in m.tracks) and len(seen) == len(set(seen))
