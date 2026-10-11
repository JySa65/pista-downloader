import pytest

from youtube_download.core.downloader import ARCHIVES, format_opts


def test_audio_extracts_mp3_at_kbps():
    opts = format_opts("audio", "256")
    assert opts["format"] == "bestaudio/best"
    assert opts["writethumbnail"] is True
    assert [pp["key"] for pp in opts["postprocessors"]] == [
        "FFmpegThumbnailsConvertor", "FFmpegExtractAudio", "FFmpegMetadata", "EmbedThumbnail"
    ]
    assert opts["postprocessors"][0] == {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}
    assert opts["postprocessors"][1] == {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "256"}
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


def test_base_opts_wires_tools_retries_and_logger():
    from youtube_download.core.downloader import base_opts

    logger = object()
    opts = base_opts(ffmpeg="/ff", deno="/d/deno", logger=logger)
    assert opts["ffmpeg_location"] == "/ff"
    assert opts["js_runtimes"] == {"deno": {"path": "/d/deno"}}
    assert opts["logger"] is logger
    assert opts["retries"] >= 5 and opts["fragment_retries"] >= 5 and opts["extractor_retries"] >= 3
    assert opts["windowsfilenames"] is True and opts["noprogress"] is True


def test_base_opts_without_tools_leaves_yt_dlp_defaults():
    from youtube_download.core.downloader import base_opts

    opts = base_opts(ffmpeg=None, deno=None, logger=None)
    assert "ffmpeg_location" not in opts and "js_runtimes" not in opts and "logger" not in opts
