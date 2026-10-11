"""Local library: find MP3/MP4 files, read embedded covers, guess artist from 'Artist - Title' names."""
import re
from pathlib import Path

from mutagen import MutagenError  # installed with yt-dlp[default]; used by yt-dlp itself to embed covers
from mutagen.id3 import ID3, ID3NoHeaderError

MEDIA = {".mp3", ".mp4"}


def scan(folder: str | Path) -> list[Path]:
    root = Path(folder).expanduser()
    if not root.is_dir():
        return []
    files = (p for p in root.rglob("*") if p.suffix.lower() in MEDIA and p.is_file())
    return sorted(files, key=lambda p: p.relative_to(root).as_posix().lower())


def cover_bytes(path: str | Path) -> tuple[bytes, str] | None:
    """(image bytes, mime) of the cover embedded in an MP3 by yt-dlp's EmbedThumbnail, or None."""
    try:
        pics = ID3(path).getall("APIC")
    except (ID3NoHeaderError, OSError, MutagenError):
        return None
    return (pics[0].data, pics[0].mime or "image/jpeg") if pics else None


def split_artist(stem: str) -> tuple[str, str]:
    """('Artist', 'Title') from 'Artist - Title'; ('', stem) when there is no dash."""
    parts = re.split(r"\s+[-–—]\s+", stem, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", stem)
