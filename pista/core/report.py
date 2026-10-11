"""«Reportar un problema»: GitHub issue form URL prefilled with the app version and OS."""
import platform
from urllib.parse import urlencode

REPO = "JySa65/pista-downloader"


def os_label(system: str, release: str, version: str, mac_ver: str = "") -> str:
    if system == "Windows":
        build = int(version.rsplit(".", 1)[-1]) if version.rsplit(".", 1)[-1].isdigit() else 0
        return f"Windows {'11' if build >= 22000 else release} ({version})"  # Windows 11 still reports release '10'
    if system == "Darwin":
        return f"macOS {mac_ver}".strip()
    return f"{system} {release}".strip()


def current_os() -> str:
    return os_label(platform.system(), platform.release(), platform.version(), platform.mac_ver()[0])


def issue_url(version: str, os_text: str) -> str:
    """Issue form prefill: `template` plus field ids from .github/ISSUE_TEMPLATE/bug_report.yml."""
    query = urlencode({"template": "bug_report.yml", "version": version, "os_version": os_text})
    return f"https://github.com/{REPO}/issues/new?{query}"
