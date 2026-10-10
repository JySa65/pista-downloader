"""OS-specific helpers, kept pure (platform and `which` are injectable) for testing."""
import shutil
import subprocess
import sys
from collections.abc import Callable
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


def has_ffmpeg(which: Which = shutil.which) -> bool:
    return which("ffmpeg") is not None
