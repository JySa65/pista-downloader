"""«Buscar actualizaciones»: compare the latest GitHub release with the running version."""
import json
import re
import urllib.request

from .report import REPO

RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?", (text or "").strip())
    return (int(m[1]), int(m[2]), int(m[3] or 0)) if m else None


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def fetch_latest(timeout: float = 8.0, url: str = RELEASES_API) -> dict | None:
    """Latest release JSON, or None on any error (offline, rate limit, 404 while the repo is private)."""
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                        "User-Agent": "pista-update-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except (OSError, ValueError):
        return None


def update_status(release: dict | None, current: str) -> tuple[str, str, str | None]:
    """(kind: new|latest|error, message, release page url)."""
    if not release or not release.get("tag_name"):
        return ("error", "No se pudo comprobar si hay actualizaciones. Revisa tu conexión o inténtalo más tarde.", None)
    tag = release["tag_name"]
    if is_newer(tag, current):
        return ("new", f"Hay una versión nueva: {tag}", release.get("html_url"))
    return ("latest", "Tienes la última versión.", None)
