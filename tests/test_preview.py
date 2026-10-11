from pathlib import Path

from pista.core.downloader import preview_clip, preview_clip_path


def test_preview_clip_path_is_per_video_id(tmp_path):
    url = "https://www.youtube.com/watch?v=AAAAAAAAAAA&list=RDxyz&start_radio=1"
    assert preview_clip_path(url, tmp_path) == tmp_path / "AAAAAAAAAAA.mp4"
    assert preview_clip_path("https://youtu.be/AAAAAAAAAAA", tmp_path) == tmp_path / "AAAAAAAAAAA.mp4"


def test_preview_clip_returns_cached_file_without_network(tmp_path):
    cached = tmp_path / "AAAAAAAAAAA.mp4"
    cached.write_bytes(b"x")
    assert preview_clip("https://youtu.be/AAAAAAAAAAA", tmp_path) == cached
