import pytest

from pista.core.urls import classify, video_url

MIX = "https://www.youtube.com/watch?v=AAAAAAAAAAA&list=RDTESTMIX0123456789&start_radio=1"


@pytest.mark.parametrize(
    "url, kind",
    [
        ("https://www.youtube.com/watch?v=AAAAAAAAAAA", "video"),
        ("https://youtu.be/AAAAAAAAAAA", "video"),
        ("https://youtu.be/AAAAAAAAAAA?si=abc", "video"),
        ("https://music.youtube.com/watch?v=AAAAAAAAAAA", "video"),
        ("https://www.youtube.com/playlist?list=PLabc123", "playlist"),
        ("https://www.youtube.com/watch?v=AAAAAAAAAAA&list=PLabc123&index=3", "playlist"),
        ("https://music.youtube.com/playlist?list=OLAK5uy_abc", "playlist"),
        ("https://youtu.be/AAAAAAAAAAA?list=PLabc123", "playlist"),
        (MIX, "mix"),
        ("https://music.youtube.com/watch?v=AAAAAAAAAAA&list=RDAMVMAAAAAAAAAAA", "mix"),
    ],
)
def test_classify(url, kind):
    assert classify(url) == kind


@pytest.mark.parametrize(
    "url",
    [
        MIX,
        "https://www.youtube.com/watch?v=AAAAAAAAAAA&list=PLabc123&index=3",
        "https://youtu.be/AAAAAAAAAAA?list=PLabc123&t=10",
        "https://music.youtube.com/watch?v=AAAAAAAAAAA",
    ],
)
def test_video_url_strips_list_params(url):
    assert video_url(url) == "https://www.youtube.com/watch?v=AAAAAAAAAAA"


def test_video_url_leaves_unknown_urls_alone():
    assert video_url("https://example.com/x") == "https://example.com/x"


# --- YouTube-only (defense in depth against crafted pages via yt-dlp's generic extractor) ---
from pista.core.urls import is_youtube  # noqa: E402


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=AAAAAAAAAAA",
    "https://youtube.com/watch?v=AAAAAAAAAAA",
    "https://m.youtube.com/watch?v=AAAAAAAAAAA",
    "https://music.youtube.com/watch?v=AAAAAAAAAAA&list=RDAMVMAAAAAAAAAAA",
    "https://www.youtube.com/playlist?list=PLabc123",
    "https://www.youtube.com/shorts/AAAAAAAAAAA",
    "https://youtu.be/AAAAAAAAAAA?si=x",
    "http://www.youtube.com/watch?v=AAAAAAAAAAA",
])
def test_is_youtube_accepts_youtube_hosts(url):
    assert is_youtube(url)


@pytest.mark.parametrize("url", [
    "https://example.com/song.html",
    "https://www.youtube.com.evil.example/watch?v=AAAAAAAAAAA",
    "https://evil-youtube.com/watch?v=AAAAAAAAAAA",
    "https://youtu.be.evil.example/AAAAAAAAAAA",
    "https://user@evil.example/?x=youtube.com",
    "javascript:alert(1)",
    "file:///etc/passwd",
    "ftp://www.youtube.com/watch?v=AAAAAAAAAAA",
    "",
])
def test_is_youtube_rejects_everything_else(url):
    assert not is_youtube(url)


def test_yt_dlp_restricted_to_youtube_extractors():
    from yt_dlp.extractor import gen_extractor_classes

    from pista.core.downloader import ALLOWED_EXTRACTORS, base_opts

    assert base_opts(None, None, None)["allowed_extractors"] == ALLOWED_EXTRACTORS
    by_name = {ie.IE_NAME.lower(): ie for ie in gen_extractor_classes()}
    assert set(ALLOWED_EXTRACTORS) <= set(by_name)  # names exist in the installed yt-dlp
    allowed = [by_name[n] for n in ALLOWED_EXTRACTORS]
    for url in ["https://www.youtube.com/watch?v=AAAAAAAAAAA", "https://youtu.be/AAAAAAAAAAA",
                "https://www.youtube.com/shorts/AAAAAAAAAAA", "https://music.youtube.com/watch?v=AAAAAAAAAAA",
                "https://www.youtube.com/playlist?list=PLabc123",
                "https://www.youtube.com/watch?v=AAAAAAAAAAA&list=RDTESTMIX0123456789"]:
        assert any(ie.suitable(url) for ie in allowed), url
    assert not any(ie.suitable("https://example.com/song.html") for ie in allowed)
