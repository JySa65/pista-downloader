"""3: malformed, partial, huge and hostile listing metadata (fake yt-dlp, no network)."""
import pytest

import pista.core.downloader as dl
from pista.core.queue import QueueModel

from .conftest import PAYLOAD


class FakeYDL:
    def __init__(self, info):
        self.info, self.opts = info, None

    def __call__(self, opts):
        self.opts = opts
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        if isinstance(self.info, Exception):
            raise self.info
        return self.info


@pytest.fixture
def fake(monkeypatch):
    def install(info):
        f = FakeYDL(info)
        monkeypatch.setattr(dl, "_ydl", f)
        return f
    return install


def test_playlist_with_none_entries_and_missing_fields(fake):
    fake({"_type": "playlist", "title": None, "id": "PLx", "entries": [
        None,
        {"id": "AAAAAAAAAAA"},  # no title/duration/thumbnail/channel
        {"id": "BBBBBBBBBBB", "title": "", "duration": None, "thumbnails": []},
        {"id": "CCCCCCCCCCC", "title": "ok", "duration": 61.5, "thumbnails": [{"url": "https://i.ytimg.com/x.jpg"}]},
    ]})
    tracks = dl.list_tracks("https://www.youtube.com/playlist?list=PLx", "playlist")
    assert [t.id for t in tracks] == ["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"]
    assert tracks[0].title == "(sin título)" and tracks[0].channel == "?" and tracks[0].duration is None
    assert tracks[2].thumbnail == "https://i.ytimg.com/x.jpg" and tracks[0].playlist == "PLx"


def test_huge_playlist_and_duplicates(fake):
    entries = [{"id": f"{i:011d}", "title": f"t{i}"} for i in range(5000)] + [{"id": "00000000007", "title": "dup"}]
    fake({"_type": "playlist", "title": "Grande", "entries": entries})
    tracks = dl.list_tracks("https://www.youtube.com/playlist?list=PLbig", "playlist")
    m = QueueModel()
    assert m.add_tracks(tracks) == 5000  # duplicate id collapsed
    assert len(m.tracks) == 5000 and m.counts()["queued"] == 5000


def test_mix_limit_is_passed_to_yt_dlp(fake):
    f = fake({"_type": "playlist", "title": "Mix", "entries": []})
    dl.list_tracks("https://www.youtube.com/watch?v=AAAAAAAAAAA&list=RDx", "mix", 7)
    assert f.opts["playlistend"] == 7 and f.opts["extract_flat"] == "in_playlist"


@pytest.mark.parametrize("title", [
    PAYLOAD, "🎵" * 300, "مرحبا بالعالم " * 40, "x" * 600, "CON", "NUL.mp3", "..", "a/b\\c", "‮evil",
])
def test_hostile_titles_survive_listing(fake, title):
    fake({"id": "AAAAAAAAAAA", "title": title, "duration": 1})
    (t,) = dl.list_tracks("https://youtu.be/AAAAAAAAAAA", "video")
    assert t.title == title


def test_listing_errors_propagate_for_the_ui_to_report(fake):
    from yt_dlp.utils import DownloadError
    fake(DownloadError("ERROR: [youtube] AAAAAAAAAAA: HTTP Error 429: Too Many Requests"))
    with pytest.raises(DownloadError):
        dl.list_tracks("https://youtu.be/AAAAAAAAAAA", "video")


def test_entries_without_id_use_the_url_or_are_dropped(fake):
    fake({"_type": "playlist", "title": "L", "entries": [
        {"url": "https://www.youtube.com/watch?v=DDDDDDDDDDD", "title": "from url"},
        {"url": "https://www.youtube.com/watch?v=EEEEEEEEEEE", "title": "also from url"},
        {"title": "no id, no url"},
        {"url": "https://example.com/x", "title": "not youtube"},
    ]})
    tracks = dl.list_tracks("https://www.youtube.com/playlist?list=PLx", "playlist")
    assert [t.id for t in tracks] == ["DDDDDDDDDDD", "EEEEEEEEEEE"]
    assert all(t.url.startswith("https://www.youtube.com/watch?v=") for t in tracks)
