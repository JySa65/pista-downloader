"""OS-specific helpers, kept pure (platform and `which` are injectable) for testing."""
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from functools import cache
from pathlib import Path

Which = Callable[[str], str | None]

_CLIPBOARD = {
    "darwin": [["pbpaste"]],
    "win32": [["powershell", "-NoProfile", "-Command", "Get-Clipboard"]],
    "linux": [["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "-b"]],
}


def clipboard_commands(platform: str = sys.platform, which: Which = shutil.which) -> list[list[str]]:
    """Installed clipboard-read commands for this OS, in preference order."""
    key = "linux" if platform.startswith(("linux", "freebsd")) else platform
    return [cmd for cmd in _CLIPBOARD.get(key, []) if which(cmd[0])]


def read_clipboard() -> str | None:
    """Clipboard text, or None if no command worked."""
    for cmd in clipboard_commands():
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if res.returncode == 0:
            return res.stdout
    return None


def default_outdir(home: Path | None = None) -> Path:
    home = home or Path.home()
    return next((p for p in (home / "Music", home / "Downloads") if p.is_dir()), home)


APP_NAME = "YouTubeDownload"


def bundled_dirs(frozen: bool, meipass: str | None, executable: str) -> list[Path]:
    """Where a frozen (PyInstaller) build keeps its bundled ffmpeg; empty when running from source."""
    if not frozen:
        return []
    roots = [Path(meipass)] if meipass else []
    roots.append(Path(executable).parent)
    return [d for root in roots for d in (root / "ffmpeg", root)]


def ffmpeg_location(search_dirs: list[Path], which: Which = shutil.which, platform: str = sys.platform) -> str | None:
    """Directory holding ffmpeg: bundled first, then PATH; None if missing."""
    exe = "ffmpeg.exe" if platform == "win32" else "ffmpeg"
    for d in search_dirs:
        if (d / exe).is_file():
            return str(d)
    found = which("ffmpeg")
    return str(Path(found).parent) if found else None


@cache
def find_ffmpeg() -> str | None:
    dirs = bundled_dirs(getattr(sys, "frozen", False), getattr(sys, "_MEIPASS", None), sys.executable)
    return ffmpeg_location(dirs)


def has_ffmpeg() -> bool:
    return find_ffmpeg() is not None


def user_cache_dir(platform: str = sys.platform, env: Mapping[str, str] = os.environ,
                   home: Path | None = None) -> Path:
    """Per-user writable cache dir (never inside the app bundle)."""
    home = home or Path.home()
    if platform == "win32":
        return Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / APP_NAME / "Cache"
    if platform == "darwin":
        return home / "Library" / "Caches" / APP_NAME
    return Path(env.get("XDG_CACHE_HOME") or home / ".cache") / APP_NAME
