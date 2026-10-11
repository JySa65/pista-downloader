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
