"""Which URLs the app may open in the user's browser.

Video URLs and release pages come from data fetched over the network (yt-dlp metadata, the GitHub API),
so they are checked before being handed to the OS: https only, exact host, no credentials.
"""
import posixpath
from urllib.parse import urlparse

from .report import REPO
from .urls import YOUTUBE_HOSTS

APP_HOSTS = {"github.com", "jysa65.dev"}


def _https(url: str | None):
    try:
        p = urlparse((url or "").strip())
    except ValueError:
        return None
    if p.scheme != "https" or p.username or p.password or not p.hostname:
        return None
    return p


def is_video_url(url: str | None) -> bool:
    p = _https(url)
    return bool(p) and p.hostname.lower() in YOUTUBE_HOSTS


def is_release_url(url: str | None) -> bool:
    p = _https(url)
    if not p or p.hostname.lower() != "github.com":
        return False
    path = posixpath.normpath(p.path)
    return path == p.path.rstrip("/") and path.startswith(f"/{REPO}/releases/")


def is_trusted(url: str | None) -> bool:
    """Links built into the app (author, license, issues) or checked video/release links."""
    p = _https(url)
    return bool(p) and (p.hostname.lower() in APP_HOSTS or is_video_url(url))


def open_url(url: str | None, check=is_trusted) -> bool:
    """Open in the default browser only if `check(url)` passes; returns whether it was opened."""
    import webbrowser

    if not check(url):
        return False
    return bool(webbrowser.open(url))
