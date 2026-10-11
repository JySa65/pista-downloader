"""Local library: find MP3/MP4 files, read embedded covers, guess artist from 'Artist - Title' names."""
import random
import re
from dataclasses import dataclass
from pathlib import Path

import mutagen
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


# --- Reproductor: metadata, groups, sorting, prev/next -------------------------------------------------

@dataclass(frozen=True)
class Entry:
    path: Path
    fmt: str  # "MP3" | "MP4"
    title: str
    artist: str  # "—" when unknown (never the folder name)
    duration: float | None


def read_meta(path: Path) -> tuple[str | None, str | None, float | None]:
    """(title, artist, seconds) from the file's tags/container; Nones when unreadable."""
    try:
        f = mutagen.File(path)
    except Exception:  # noqa: BLE001 — a corrupt file must not break the list
        f = None
    if f is None:
        try:  # e.g. an MP3 whose audio can't be parsed: its ID3 tags may still be fine (no duration)
            tags = ID3(path) if path.suffix.lower() == ".mp3" else {}
        except Exception:  # noqa: BLE001
            return None, None, None
        f = type("NoInfo", (), {"tags": tags, "info": None})()
    tags = f.tags or {}

    def first(*keys):
        for k in keys:
            try:
                v = tags.get(k)
            except (ValueError, KeyError):
                v = None
            if v:
                v = v.text if hasattr(v, "text") else v
                v = v[0] if isinstance(v, list) and v else v
                if str(v).strip():
                    return str(v).strip()
        return None

    length = getattr(getattr(f, "info", None), "length", None)
    return first("TIT2", "\xa9nam"), first("TPE1", "\xa9ART", "aART"), (float(length) if length else None)


def entry_for(path: Path, meta: tuple[str | None, str | None, float | None]) -> Entry:
    """Fallback order: tags → «Artist - Title» file name → «—»."""
    title, artist, duration = meta
    name_artist, name_title = split_artist(path.stem)
    title = (title or "").strip() or name_title
    artist = (artist or "").strip() or name_artist or "—"
    return Entry(path, "MP4" if path.suffix.lower() == ".mp4" else "MP3", title, artist, duration)


class MetaCache(dict):
    """(path, mtime_ns, size) → metadata, so rescanning a big library only reads changed files."""


def load_library(folder: str | Path, cache: MetaCache) -> list[Entry]:
    """Scan and read metadata (call off the event loop)."""
    entries = []
    for p in scan(folder):
        try:
            st = p.stat()
        except OSError:
            continue
        key = (str(p), st.st_mtime_ns, st.st_size)
        if key not in cache:
            cache[key] = read_meta(p)
        entries.append(entry_for(p, cache[key]))
    return entries


def _matches(e: Entry, q: str) -> bool:
    return not q or q in f"{e.title} {e.artist} {e.path.name}".lower()


def counts(entries: list[Entry], query: str = "") -> dict[str, int]:
    q = query.strip().lower()
    shown = [e for e in entries if _matches(e, q)]
    return {"all": len(shown), "mp3": sum(e.fmt == "MP3" for e in shown), "mp4": sum(e.fmt == "MP4" for e in shown)}


_SORT = {
    "title": lambda e: (e.title.lower(),),
    "artist": lambda e: (e.artist == "—", e.artist.lower(), e.title.lower()),
    "duration": lambda e: (e.duration is None, e.duration or 0),
}


def library_view(entries: list[Entry], query: str = "", mode: str = "all", sort: str = "title",
                 desc: bool = False) -> list[tuple[str | None, list[Entry]]]:
    """Sections to show: «Todos» → MP3 then MP4 with headers; «MP3»/«MP4» → one section without header."""
    q = query.strip().lower()
    key = _SORT.get(sort, _SORT["title"])
    sections = []
    for fmt in ("MP3", "MP4"):
        if mode != "all" and mode != fmt.lower():
            continue
        rows = [e for e in entries if e.fmt == fmt and _matches(e, q)]
        if sort == "duration" and desc:  # keep unknown durations last in both directions
            rows.sort(key=lambda e: (e.duration is None, -(e.duration or 0)))
        else:
            rows.sort(key=key, reverse=desc)
        if rows:
            sections.append((f"{fmt} · {len(rows)}" if mode == "all" else None, rows))
    return sections


def visible(sections: list[tuple[str | None, list[Entry]]]) -> list[Entry]:
    return [e for _, rows in sections for e in rows]


def next_entry(shown: list[Entry], current: Path | None, d: int, shuffle: bool = False,
               rng: random.Random | None = None) -> Entry | None:
    """Prev/next/shuffle within the visible list; if the playing file is filtered out, start from the top."""
    if not shown:
        return None
    if shuffle:
        return (rng or random).choice(shown)
    paths = [e.path for e in shown]
    if current not in paths:
        return shown[0] if d >= 0 else shown[-1]
    return shown[(paths.index(current) + d) % len(shown)]
