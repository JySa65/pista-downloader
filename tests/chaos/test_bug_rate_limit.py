from yt_dlp.utils import DownloadError

from pista.core.batch import is_rate_limited
from pista.core.downloader import base_opts

from .conftest import model_with, run, runner


def test_rate_limit_detection():
    assert is_rate_limited("ERROR: [youtube] x: HTTP Error 429: Too Many Requests")
    assert is_rate_limited("Sign in to confirm you’re not a bot. Use --cookies-from-browser")
    assert not is_rate_limited("HTTP Error 403: Forbidden")


def test_batch_backs_off_after_429_instead_of_hammering():
    def download(t, *a):
        raise DownloadError("ERROR: [youtube] x: HTTP Error 429: Too Many Requests")

    m = model_with(4)
    r = runner(m, download, retry_delay=0)
    run(r.run())
    assert r.sleep.total >= 15 + 30 + 60 + 120  # growing pause after each rate-limited item
    assert any("Demasiadas solicitudes" in msg for _, msg in r.logs)


def test_yt_dlp_retries_sleep_between_attempts():
    fns = base_opts(None, None, None)["retry_sleep_functions"]
    assert set(fns) >= {"http", "fragment", "extractor"}
    assert fns["http"](0) >= 1 and fns["http"](5) > fns["http"](1) and fns["http"](50) <= 60


def test_stop_interrupts_the_backoff():
    def download(t, *a):
        raise DownloadError("ERROR: HTTP Error 429: Too Many Requests")

    m = model_with(3)
    r = runner(m, download)
    calls = []

    async def sleep(seconds):
        calls.append(seconds)
        if len(calls) == 3:
            r.stop()

    r.sleep = sleep
    run(r.run())
    assert len(calls) == 3  # stopped within the first pause, no more waiting or downloads
    assert [m.state[t.id][0] for t in m.tracks] == ["error", "stopped", "stopped"]
