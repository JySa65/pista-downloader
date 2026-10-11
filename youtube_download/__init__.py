"""YouTube downloader desktop app."""
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
