from urllib.parse import parse_qs, urlparse


def _parts(url: str) -> tuple[str | None, str | None]:
    """Return (video_id, list_id) for a YouTube URL."""
    p = urlparse(url.strip())
    qs = parse_qs(p.query)
    vid = qs.get("v", [None])[0]
    if p.netloc.endswith("youtu.be"):
        vid = p.path.strip("/") or None
    return vid, qs.get("list", [None])[0]


def classify(url: str) -> str:
    """'video', 'playlist' or 'mix' (auto-generated radio, list=RD...)."""
    _, list_id = _parts(url)
    if not list_id:
        return "video"
    return "mix" if list_id.startswith("RD") else "playlist"


def video_id(url: str) -> str | None:
    return _parts(url)[0]


def video_url(url: str) -> str:
    """Canonical watch URL without list/index/start_radio params."""
    vid = video_id(url)
    return f"https://www.youtube.com/watch?v={vid}" if vid else url.strip()
