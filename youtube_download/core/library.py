"""Local MP3 library: find files and guess artist from 'Artist - Title' names."""
import re
from pathlib import Path


def scan(folder: str | Path) -> list[Path]:
    root = Path(folder).expanduser()
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.mp3"), key=lambda p: p.relative_to(root).as_posix().lower())


def split_artist(stem: str) -> tuple[str, str]:
    """('Artist', 'Title') from 'Artist - Title'; ('', stem) when there is no dash."""
    parts = re.split(r"\s+[-–—]\s+", stem, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", stem)
