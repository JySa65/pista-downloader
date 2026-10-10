import pytest

from youtube_download.core.downloader import ARCHIVES, format_opts


def test_audio_extracts_mp3_at_kbps():
    opts = format_opts("audio", "256")
    assert opts["format"] == "bestaudio/best"
    assert opts["postprocessors"] == [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "256"}
    ]
    assert "merge_output_format" not in opts


@pytest.mark.parametrize("res, height", [("360p", 360), ("720p", 720), ("1080p", 1080), ("4K", 2160)])
def test_video_caps_height_and_merges_mp4(res, height):
    opts = format_opts("video", res)
    assert opts["format"] == f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/b[height<={height}]"
    assert opts["merge_output_format"] == "mp4"
    assert "postprocessors" not in opts


def test_unknown_format_rejected():
    with pytest.raises(ValueError):
        format_opts("gif", "1")


def test_separate_archive_per_format():
    assert ARCHIVES == {"audio": ".downloaded-audio.txt", "video": ".downloaded-video.txt"}
