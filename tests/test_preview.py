from pathlib import Path

from youtube_download.core.downloader import preview_clip, preview_clip_path


def test_preview_clip_path_is_per_video_id(tmp_path):
    url = "https://www.youtube.com/watch?v=VIDEOID0001&list=RDxyz&start_radio=1"
    assert preview_clip_path(url, tmp_path) == tmp_path / "VIDEOID0001.mp4"
    assert preview_clip_path("https://youtu.be/VIDEOID0001", tmp_path) == tmp_path / "VIDEOID0001.mp4"


def test_preview_clip_returns_cached_file_without_network(tmp_path):
    cached = tmp_path / "VIDEOID0001.mp4"
    cached.write_bytes(b"x")
    assert preview_clip("https://youtu.be/VIDEOID0001", tmp_path) == cached
