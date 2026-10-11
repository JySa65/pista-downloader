"""Fewer, paced YouTube requests: options, global gate/breaker, info reuse, archive pre-skip, update once."""
import pytest
from yt_dlp.utils import DownloadError

import pista.core.downloader as dl
import pista.core.updates as up
from pista.core.breaker import Breaker, CooldownActive, YouTubeGate
from pista.core.models import Track
from pista.core.plan import plan_download
from pista.core.queue import BatchRunner, QueueModel


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def gate(monkeypatch):
    clock = Clock()
    g = YouTubeGate(Breaker(clock=clock))
    g.clock = clock
    monkeypatch.setattr(dl, "GATE", g)
    return g


class FakeYDL:
    calls: list = []
    behavior = None

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def add_post_processor(self, pp, when="post_process"):

        pass

    def extract_info(self, url, download=False):
        FakeYDL.calls.append(("extract", url, download))
        if FakeYDL.behavior:
            raise FakeYDL.behavior
        return {"id": "AAAAAAAAAAA", "title": "t", "duration": 10,
                "requested_downloads": [{"filepath": "/o/t.mp3"}] if download else None}

    def process_ie_result(self, info, download=True):
        FakeYDL.calls.append(("process", info["id"], download))
        return {**info, "requested_downloads": [{"filepath": "/o/t.mp3"}]}

    @staticmethod
    def sanitize_info(info):
        return dict(info)


@pytest.fixture
def fake(monkeypatch):
    FakeYDL.calls, FakeYDL.behavior = [], None
    monkeypatch.setattr(dl, "_ydl", FakeYDL)
    return FakeYDL


def test_pacing_and_retry_options():
    o = dl.base_opts(None, None, None)
    assert o["sleep_interval_requests"] == 1
    assert (o["sleep_interval"], o["max_sleep_interval"]) == (2, 5)
    assert o["extractor_retries"] == 1  # don't let yt-dlp hammer on 429; the breaker handles it
    assert o["retries"] >= 5 and o["fragment_retries"] >= 5  # still resilient to network drops


def test_rate_limit_trips_the_breaker_and_blocks_all_youtube_calls(gate, fake):
    fake.behavior = DownloadError("ERROR: [youtube] x: HTTP Error 429: Too Many Requests")
    with pytest.raises(DownloadError):
        dl.list_tracks("https://youtu.be/AAAAAAAAAAA", "video")
    assert gate.breaker.is_open()
    fake.behavior, n = None, len(fake.calls)
    with pytest.raises(CooldownActive):
        dl.list_tracks("https://youtu.be/AAAAAAAAAAA", "video")
    with pytest.raises(CooldownActive):
        dl.download(Track("AAAAAAAAAAA", "t", "c", 1, "https://youtu.be/AAAAAAAAAAA", None), "/tmp/o")
    with pytest.raises(CooldownActive):
        dl.preview_clip("https://youtu.be/BBBBBBBBBBB", "/tmp/nonexistent-preview-dir")
    assert len(fake.calls) == n  # zero network while cooling down
    gate.clock.t += 121
    dl.list_tracks("https://youtu.be/AAAAAAAAAAA", "video")
    assert gate.breaker.next_cooldown == 120  # success resets the cooldown


def test_downloads_do_not_reuse_listing_stream_urls(gate, fake, tmp_path):
    """Measured live: reusing the listing's info for the download got HTTP 403 (stream URLs are tied to the
    extraction session). Each download extracts fresh."""
    (t,) = dl.list_tracks("https://youtu.be/AAAAAAAAAAA", "video")
    dl.download(t, tmp_path)
    assert [c[0] for c in fake.calls] == ["extract", "extract"] and not hasattr(dl, "_INFO")


def test_only_the_reliable_thumbnail_is_fetched():
    from pista.core.downloader import ReliableThumbnail
    info = {"id": "AAAAAAAAAAA", "thumbnails": [
        {"url": "https://i.ytimg.com/vi/AAAAAAAAAAA/maxresdefault.jpg", "preference": 0},
        {"url": "https://i.ytimg.com/vi_webp/AAAAAAAAAAA/sddefault.webp", "preference": -1},
        {"url": "https://i.ytimg.com/vi/AAAAAAAAAAA/hqdefault.jpg", "preference": -5},
        {"url": "https://i.ytimg.com/vi/AAAAAAAAAAA/hq720.jpg", "preference": -2},
    ]}
    _, out = ReliableThumbnail().run(info)
    assert [t["url"].rsplit("/", 1)[1] for t in out["thumbnails"]] == ["hqdefault.jpg"]
    _, untouched = ReliableThumbnail().run({"thumbnails": [{"url": "https://x/y.jpg"}]})
    assert len(untouched["thumbnails"]) == 1  # nothing better known: leave yt-dlp's choice


def test_downloads_register_the_thumbnail_trim(gate, monkeypatch, tmp_path):
    added = []

    class Fake(FakeYDL):
        def add_post_processor(self, pp, when="post_process"):
            added.append((type(pp).__name__, when))

    monkeypatch.setattr(dl, "_ydl", Fake)
    Fake.calls, Fake.behavior = [], None
    dl.download(Track("AAAAAAAAAAA", "t", "c", 1, "https://youtu.be/AAAAAAAAAAA", None), tmp_path)
    assert ("ReliableThumbnail", "pre_process") in added


def test_archived_items_cost_zero_network_calls():
    calls = []
    m = QueueModel()
    tracks = [Track(f"{c * 11}", c, "", 1, f"https://www.youtube.com/watch?v={c * 11}", None) for c in "AB"]
    m.add_tracks(tracks)
    plan = plan_download([(t, "queued", True) for t in tracks], "audio", "192", archived={"A" * 11}, running=False,
                         consent=True)
    for tid in plan.skip:
        m.set_state(tid, "skipped")
    import asyncio
    asyncio.run(BatchRunner(m, lambda t, *a: calls.append(t.id), out="/o", quality="192", fmt="audio").run())
    assert calls == ["B" * 11]


def test_update_check_runs_at_most_once_per_session(monkeypatch):
    n = []
    monkeypatch.setattr(up, "_session_result", None)
    fetch = lambda: n.append(1) or {"tag_name": "v9.9.9", "html_url": "https://github.com/JySa65/pista-downloader/releases/tag/v9.9.9"}
    a = up.check_for_updates("0.3.1", fetch=fetch)
    b = up.check_for_updates("0.3.1", fetch=fetch)
    assert a == b and a[0] == "new" and len(n) == 1
