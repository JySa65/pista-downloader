"""User choices that survive a restart (only choices: never cookies or other secrets)."""
import json
import os
import sys
from pathlib import Path

DEFAULTS = {"cookies": False, "browser": "firefox"}

# (yt-dlp browser key, label). Safari exists only on macOS.
_BROWSERS = [("firefox", "Firefox"), ("chrome", "Chrome"), ("edge", "Edge"), ("brave", "Brave"),
             ("safari", "Safari"), ("opera", "Opera"), ("vivaldi", "Vivaldi"), ("chromium", "Chromium")]


def browsers_for(platform: str = sys.platform) -> list[tuple[str, str]]:
    return [(k, label) for k, label in _BROWSERS if k != "safari" or platform == "darwin"]


def load_settings(path: Path) -> dict:
    """Saved choices, falling back to the defaults for anything missing, corrupt or unexpected."""
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    allowed = {k for k, _ in browsers_for()}
    cookies = data.get("cookies")
    browser = data.get("browser")
    return {
        "cookies": cookies if isinstance(cookies, bool) else DEFAULTS["cookies"],
        "browser": browser if isinstance(browser, str) and browser in allowed else DEFAULTS["browser"],
    }


def save_settings(path: Path, settings: dict) -> None:
    """Best effort: a settings file that can't be written must never break the app."""
    data = {"cookies": bool(settings.get("cookies")), "browser": str(settings.get("browser", DEFAULTS["browser"]))}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data), "utf-8")
        os.replace(tmp, path)
    except OSError:
        pass
