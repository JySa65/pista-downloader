"""Rate limits (429 / bot check) pause the whole batch via the global breaker; items stay queued, not Error."""
from yt_dlp.utils import DownloadError

from pista.core.batch import is_rate_limited
from pista.core.breaker import Breaker, CooldownActive
from pista.core.downloader import base_opts

from .conftest import model_with, run, runner

RL = "ERROR: [youtube] x: HTTP Error 429: Too Many Requests"


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def paced_runner(m, download):
    clock = Clock()
    b = Breaker(clock=clock)
    r = runner(m, download, breaker=b, retry_delay=0)

    async def sleep(seconds):  # fake time: each sleep advances the breaker clock
        r.sleep_log.append((seconds, r.current, b.is_open()))
        clock.t += seconds

    r.sleep_log = []
    r.sleep = sleep
    return r, b, clock


def test_rate_limit_detection():
    assert is_rate_limited(RL)
    assert is_rate_limited("Sign in to confirm you’re not a bot. Use --cookies-from-browser")
    assert not is_rate_limited("HTTP Error 403: Forbidden")


def test_rate_limit_pauses_the_batch_and_the_item_stays_queued():
    attempts = []

    def download(t, *a):
        attempts.append(t.id)
        if len(attempts) == 1:
            raise DownloadError(RL)
        return None

    m = model_with(2)
    r, b, clock = paced_runner(m, download)
    summary = run(r.run())
    first = "vid00000000"
    assert attempts == [first, first, "vid00000001"]  # waited, then retried the same item
    assert m.fails.get(first) is None and summary.failed == 0 and summary.skipped == 2
    waited = sum(s for s, _, open_ in r.sleep_log if open_)
    assert 119 <= waited <= 121  # the 2 min cooldown, not a hammering loop
    assert all(cur is None for _, cur, _ in r.sleep_log)  # no row shown «running» while paused
    assert any("Reanudando en" in msg for _, msg in r.logs)


def test_cooldown_from_another_activity_also_pauses_the_batch():
    calls = []

    def download(t, *a):
        calls.append(t.id)
        if len(calls) == 1:
            raise CooldownActive("YouTube limitó las peticiones. Reanudando en 1:00…")
        return None

    m = model_with(1)
    r, b, clock = paced_runner(m, download)
    b.trip()
    summary = run(r.run())
    assert summary.skipped == 1 and m.fails.get("vid00000000") is None


def test_manual_resume_and_stop_during_the_cooldown():
    def download(t, *a):
        raise DownloadError(RL)

    m = model_with(2)
    r, b, clock = paced_runner(m, download)

    async def sleep(seconds):
        r.stop()  # «Detener» while paused

    r.sleep = sleep
    summary = run(r.run())
    assert [m.state[t.id][0] for t in m.tracks] == ["stopped", "stopped"] and summary.failed == 0


def test_resume_now_skips_the_rest_of_the_wait():
    attempts = []

    def download(t, *a):
        attempts.append(t.id)
        if len(attempts) == 1:
            raise DownloadError(RL)
        return None

    m = model_with(1)
    r, b, clock = paced_runner(m, download)
    waits = []

    async def sleep(seconds):
        waits.append(seconds)
        b.resume()  # «Reanudar ahora»

    r.sleep = sleep
    run(r.run())
    assert len(waits) == 1 and attempts == ["vid00000000", "vid00000000"]


def test_yt_dlp_retries_sleep_between_attempts():
    fns = base_opts(None, None, None)["retry_sleep_functions"]
    assert set(fns) >= {"http", "fragment", "extractor"}
    assert fns["http"](0) >= 1 and fns["http"](5) > fns["http"](1) and fns["http"](50) <= 60
