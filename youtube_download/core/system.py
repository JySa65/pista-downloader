"""OS-specific helpers, kept pure (platform and `which` are injectable) for testing."""
import os
import shutil
import subprocess
import sys
import sysconfig
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


def no_window(platform: str = sys.platform) -> dict:
    """subprocess kwargs that keep Windows from flashing a console window."""
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)} if platform == "win32" else {}


def read_clipboard() -> str | None:
    """Clipboard text, or None if no command worked."""
    for cmd in clipboard_commands():
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3, **no_window())
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
    """Where a frozen (PyInstaller) build keeps its bundled ffmpeg and deno; empty when running from source."""
    if not frozen:
        return []
    roots = [Path(meipass)] if meipass else []
    roots.append(Path(executable).parent)
    return [d for root in roots for d in (root / "ffmpeg", root / "deno", root)]


def tool_path(name: str, search_dirs: list[Path], which: Which = shutil.which,
              platform: str = sys.platform) -> str | None:
    """Full path of an executable: the given dirs first (bundled, venv scripts), then PATH."""
    exe = f"{name}.exe" if platform == "win32" else name
    for d in search_dirs:
        if (d / exe).is_file():
            return str(d / exe)
    return which(name)


def ffmpeg_location(search_dirs: list[Path], which: Which = shutil.which, platform: str = sys.platform) -> str | None:
    """Directory holding ffmpeg: bundled first, then PATH; None if missing."""
    found = tool_path("ffmpeg", search_dirs, which, platform)
    return str(Path(found).parent) if found else None


def _search_dirs() -> list[Path]:
    dirs = bundled_dirs(getattr(sys, "frozen", False), getattr(sys, "_MEIPASS", None), sys.executable)
    return [*dirs, Path(sysconfig.get_path("scripts"))]  # venv bin: where the `deno` wheel puts its binary


@cache
def find_ffmpeg() -> str | None:
    return ffmpeg_location(_search_dirs())


@cache
def find_deno() -> str | None:
    """Deno runs yt-dlp's YouTube JS challenge solver (yt-dlp-ejs); without it YouTube may answer 403."""
    return tool_path("deno", _search_dirs())


def open_command(platform: str, target: str) -> list[str] | None:
    """Command that opens a file/folder with the OS default app; None on Windows (os.startfile)."""
    if platform == "win32":
        return None
    return ["open" if platform == "darwin" else "xdg-open", target]


def open_path(target: str | Path) -> None:
    cmd = open_command(sys.platform, str(target))
    if cmd is None:
        os.startfile(str(target))  # type: ignore[attr-defined]  # Windows only, no console
    else:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **no_window())


def has_ffmpeg() -> bool:
    return find_ffmpeg() is not None


def log_dir() -> Path:
    return user_cache_dir() / "logs"


def user_cache_dir(platform: str = sys.platform, env: Mapping[str, str] = os.environ,
                   home: Path | None = None) -> Path:
    """Per-user writable cache dir (never inside the app bundle)."""
    home = home or Path.home()
    if platform == "win32":
        return Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local") / APP_NAME / "Cache"
    if platform == "darwin":
        return home / "Library" / "Caches" / APP_NAME
    return Path(env.get("XDG_CACHE_HOME") or home / ".cache") / APP_NAME
