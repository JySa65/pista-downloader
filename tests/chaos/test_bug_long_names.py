import pytest
import yt_dlp

import pista.core.downloader as dl
from pista.core.downloader import MAX_NAME_BYTES, target_dir

from .conftest import track


@pytest.mark.parametrize("title", ["x" * 600, "🎵" * 300, "مرحبا " * 120])
def test_long_playlist_titles_make_a_creatable_folder(tmp_path, title):
    d = target_dir(tmp_path, title)
    assert len(d.name.encode("utf-8")) <= MAX_NAME_BYTES
    d.mkdir()  # used to fail: [Errno 63] File name too long
    assert d.parent == tmp_path


@pytest.mark.parametrize("title", ["x" * 600, "🎵" * 300])
def test_long_video_titles_make_a_creatable_file_name(tmp_path, monkeypatch, title):
    seen = {}

    class Fake:
        def __init__(self, opts):
            seen["outtmpl"] = opts["outtmpl"]
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def extract_info(self, url, download=True):
            return {}

    monkeypatch.setattr(dl, "_ydl", Fake)
    dl.download(track(0, title=title), tmp_path, "192")
    with yt_dlp.YoutubeDL({"quiet": True}) as y:
        name = y.evaluate_outtmpl(seen["outtmpl"], {"title": title, "ext": "webm", "id": "x"})
    path = tmp_path / name
    assert path.parent == tmp_path and len(path.name.encode("utf-8")) <= 255
    path.write_bytes(b"")  # creatable
