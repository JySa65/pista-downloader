"""«Buscar actualizaciones»: compare the latest GitHub release with the running version."""
import json
import re
import urllib.parse
import urllib.request

from .report import REPO

RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(text) -> tuple[int, int, int] | None:
    if not isinstance(text, str):
        return None
    m = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?", text.strip())
    return (int(m[1]), int(m[2]), int(m[3] or 0)) if m else None


def is_newer(latest, current) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


class _SameHostRedirects(urllib.request.HTTPRedirectHandler):
    """Follow redirects only within the original host (no hopping to another server)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).hostname != urllib.parse.urlsplit(req.full_url).hostname:
            return None  # urllib then raises HTTPError for the 30x
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_latest(timeout: float = 8.0, url: str = RELEASES_API) -> dict | None:
    """Latest release JSON, or None on any error (offline, rate limit, 404 while the repo is private)."""
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "pista-update-check"})
    opener = urllib.request.build_opener(_SameHostRedirects)
    try:
        with opener.open(req, timeout=timeout) as r:
            data = json.loads(r.read(1_000_000))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def update_status(release, current: str) -> tuple[str, str, str | None]:
    """(kind: new|latest|error, message, release page url). Never raises on odd input."""
    tag = release.get("tag_name") if isinstance(release, dict) else None
    if parse_version(tag) is None:
        return ("error", "No se pudo comprobar si hay actualizaciones. Revisa tu conexión o inténtalo más tarde.", None)
    if is_newer(tag, current):
        url = release.get("html_url")
        return ("new", f"Hay una versión nueva: {tag}", url if isinstance(url, str) else None)
    return ("latest", "Tienes la última versión.", None)
