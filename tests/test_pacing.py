"""Fewer, paced YouTube requests: options, global gate/breaker, info reuse, archive pre-skip, update once."""
import pytest
from yt_dlp.utils import DownloadError

import pista.core.downloader as dl
import pista.core.updates as up
from pista.core.breaker import Breaker, CooldownActive, YouTubeGate
from pista.core.models import Track
from pista.core.plan import plan_download
from pista.core.queue import PACE_MAX, PACE_MIN, BatchRunner, QueueModel
from tests.chaos.conftest import track


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
    assert "sleep_interval" not in o and "max_sleep_interval" not in o  # paced by BatchRunner, not per format
    assert o["extractor_retries"] == 1  # don't let yt-dlp hammer on 429; the breaker handles it
    assert o["retries"] >= 5 and o["fragment_retries"] >= 5  # still resilient to network drops


def test_retry_backoff_takes_the_attempt_as_n_like_yt_dlp_passes_it():
    sleeps = dl.base_opts(None, None, None)["retry_sleep_functions"]
    assert set(sleeps) == {"http", "fragment", "extractor"}
    for kind, f in sleeps.items():
        assert [f(n=n) for n in (0, 1, 3, 10)] == [1, 2, 8, 60], kind  # RetryManager calls sleep_func(n=…)


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
    plan = plan_download([(t, "queued", True) for t in tracks], "audio", "192", existing={"A" * 11}, running=False,
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


def paced_batch(n, pace=(8, 15), on_sleep=None):
    """Run n successful downloads; returns (download order with sleeps between, statuses, logs)."""
    import asyncio
    events, statuses, logs = [], [], []
    m = QueueModel()
    m.add_tracks([track(i) for i in range(n)])

    async def sleep(seconds):
        events.append(seconds)
        if on_sleep:
            on_sleep(r)

    r = BatchRunner(m, lambda t, *a: events.append(t.id) or f"/o/{t.id}.mp3", out="/o", quality="192",
                    fmt="audio", sleep=sleep, pace=pace, status=statuses.append,
                    log=lambda msg, level=0: logs.append(msg))
    asyncio.run(r.run())
    return events, statuses, logs


def test_default_pace_is_8_to_15_seconds():
    assert (PACE_MIN, PACE_MAX) == (8, 15)


def test_no_pause_before_the_first_download_then_8_to_15_s_between_downloads():
    events, statuses, logs = paced_batch(3)
    assert events[0] == "vid00000000"  # the first download starts right away
    ids = [i for i, e in enumerate(events) if isinstance(e, str)]
    for a, b in zip(ids, ids[1:]):
        assert 8 <= sum(events[a + 1:b]) <= 15  # one paced pause between consecutive downloads
    assert sum(isinstance(e, str) for e in events) == 3


def test_the_pause_is_explained_in_the_status_line_and_the_log():
    _, statuses, logs = paced_batch(2, pace=(7, 7))
    assert "Pausa de 7 s antes de la siguiente canción para que YouTube no pida verificar que no eres un robot…" in statuses
    assert any("Pausa de 7 s" in s for s in statuses[1:]) and any("Pausa de 6 s" in s for s in statuses)  # countdown
    assert sum("robot" in msg for msg in logs) == 1


def test_stop_during_the_pause_ends_the_batch_promptly():
    events, statuses, _ = paced_batch(3, pace=(10, 10), on_sleep=lambda r: r.stop())
    assert [e for e in events if isinstance(e, str)] == ["vid00000000"]
    assert sum(isinstance(e, (int, float)) for e in events) == 1  # one step, not the whole 10 s
    assert statuses[-1] == "Detenido."


def test_no_pause_after_a_skipped_track_it_made_no_youtube_request():
    import asyncio
    events = []
    m = QueueModel()
    m.add_tracks([track(i) for i in range(3)])

    async def sleep(seconds):
        events.append(seconds)

    # vid00000000 is already in the archive (skipped: None), the others download.
    r = BatchRunner(m, lambda t, *a: events.append(t.id) or (None if t.id == "vid00000000" else f"/o/{t.id}.mp3"),
                    out="/o", quality="192", fmt="audio", sleep=sleep, pace=(5, 5))
    asyncio.run(r.run())
    assert events[:2] == ["vid00000000", "vid00000001"]  # skipped → next one starts right away
    assert events[2:] == [1] * 5 + ["vid00000002"]  # a done track is still followed by the pause


def test_download_never_lets_a_folder_archive_skip_it(gate, monkeypatch, tmp_path):
    """Pista decides what to skip (library registry, in the plan): «Descargar todas» must really download."""
    seen = []

    class Fake(FakeYDL):
        def __init__(self, opts):
            super().__init__(opts)
            seen.append(opts)

    monkeypatch.setattr(dl, "_ydl", Fake)
    (tmp_path / ".downloaded-audio.txt").write_text("youtube AAAAAAAAAAA\n")
    path = dl.download(Track("AAAAAAAAAAA", "t", "c", 1, "https://youtu.be/AAAAAAAAAAA", None), tmp_path)
    assert path == "/o/t.mp3" and "download_archive" not in seen[0]
    assert (tmp_path / ".downloaded-audio.txt").read_text() == "youtube AAAAAAAAAAA\n"  # legacy file untouched
