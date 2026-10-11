"""Pista: desktop app to download audio and video with yt-dlp, and play it."""
import json
import sys
import tomllib
from pathlib import Path


def version() -> str:
    """Version from pyproject.toml (bundled next to the app when frozen)."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    try:
        return tomllib.loads((root / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "dev"


def build_date(root: Path | None = None) -> str:
    """Build date written by packaging/build.py into build_info.json; 'dev' when running from source."""
    root = root or Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    try:
        return json.loads((root / "build_info.json").read_text("utf-8"))["date"]
    except (OSError, KeyError, ValueError):
        return "dev"
