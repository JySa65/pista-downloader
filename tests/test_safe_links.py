import pytest

from pista.core.links import is_release_url, is_trusted, is_video_url


@pytest.mark.parametrize("url, ok", [
    ("https://www.youtube.com/watch?v=AAAAAAAAAAA", True),
    ("https://youtu.be/AAAAAAAAAAA", True),
    ("https://music.youtube.com/watch?v=AAAAAAAAAAA", True),
    ("http://www.youtube.com/watch?v=AAAAAAAAAAA", False),  # https only
    ("https://www.youtube.com.evil.example/watch", False),
    ("javascript:alert(1)", False),
    ("file:///etc/passwd", False),
    ("https://user:pw@www.youtube.com/watch?v=AAAAAAAAAAA", False),
    ("", False),
    (None, False),
])
def test_video_urls(url, ok):
    assert is_video_url(url) is ok


@pytest.mark.parametrize("url, ok", [
    ("https://github.com/JySa65/pista-downloader/releases/tag/v0.4.0", True),
    ("https://github.com/JySa65/pista-downloader/releases/latest", True),
    ("https://github.com/JySa65/pista-downloader-evil/releases/tag/v1", False),
    ("https://github.com/someone/else/releases/tag/v1", False),
    ("https://github.com.evil.example/JySa65/pista-downloader/releases/tag/v1", False),
    ("http://github.com/JySa65/pista-downloader/releases/tag/v1", False),
    ("https://github.com/JySa65/pista-downloader/../../evil", False),
])
def test_release_urls(url, ok):
    assert is_release_url(url) is ok


def test_is_trusted_covers_app_links():
    for url in ("https://github.com/JySa65", "https://jysa65.dev/es/",
                "https://github.com/JySa65/pista-downloader/blob/main/LICENSE",
                "https://github.com/JySa65/pista-downloader/issues/new?template=bug_report.yml"):
        assert is_trusted(url)
    assert not is_trusted("https://example.com/")
