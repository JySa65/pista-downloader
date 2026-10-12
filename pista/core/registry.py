"""Library registry: per format, video id -> the file it was downloaded to, whatever the output folder.

Kept in the user config dir, so a song downloaded into one folder is known when another folder is chosen.
A song "exists" only while its file is still at the recorded path (a deleted/moved file downloads again).
"""
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from mutagen.id3 import ID3
from mutagen.mp4 import MP4

from .library import scan
from .system import user_config_dir
from .urls import is_youtube, video_id

log = logging.getLogger("pista.registry")

FORMATS = ("audio", "video")
EXT_FORMAT = {".mp3": "audio", ".mp4": "video"}
# yt-dlp's per-folder download archives written by earlier versions; they mark folders worth scanning.
LEGACY_ARCHIVES = (".downloaded-audio.txt", ".downloaded-video.txt", ".downloaded.txt")


class Registry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()  # downloads record from worker threads
        # No file yet = never bootstrapped: until bootstrap() ends, callers fall back to the legacy archives
        # and records stay in memory (an interrupted first scan runs again on the next start).
        self.ready = self.path.exists()
        self._data = self._load()

    def _load(self) -> dict[str, dict[str, str]]:
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            raw = None
        data = {fmt: {} for fmt in FORMATS}
        if isinstance(raw, dict):
            for fmt in FORMATS:
                entries = raw.get(fmt)
                if isinstance(entries, dict) and all(isinstance(k, str) and isinstance(v, str)
                                                     for k, v in entries.items()):
                    data[fmt] = entries
        return data

    def _save(self) -> None:
        """Atomic, best effort (caller holds the lock): a registry that can't be written never breaks a download."""
        if not self.ready:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False), "utf-8")
            os.replace(tmp, self.path)
        except OSError:
            log.warning("Could not save the library registry at %s", self.path, exc_info=True)

    def record(self, fmt: str, vid: str, path: str | Path) -> None:
        with self._lock:
            self._data[fmt][vid] = str(path)
            self._save()

    def path_for(self, fmt: str, vid: str) -> Path | None:
        with self._lock:
            p = self._data.get(fmt, {}).get(vid)
        return Path(p) if p else None

    def existing(self, fmt: str, ids: Iterable[str]) -> set[str]:
        """The ids whose recorded file is still there (one stat per known id)."""
        with self._lock:
            known = {vid: self._data.get(fmt, {}).get(vid) for vid in ids}
        return {vid for vid, p in known.items() if p and Path(p).is_file()}

    def bootstrap(self, roots: Iterable[str | Path]) -> int:
        """Scan MP3/MP4 files under `roots` for their embedded YouTube URL; record them, mark ready and save.

        Returns how many files were identified. Ids recorded meanwhile (live downloads) win over the scan.
        """
        started = time.monotonic()
        found: dict[str, dict[str, str]] = {fmt: {} for fmt in FORMATS}
        files = {f for root in roots for f in scan(root)}
        for f in sorted(files):
            vid = embedded_id(f)
            if vid:
                found[EXT_FORMAT[f.suffix.lower()]].setdefault(vid, str(f))
        with self._lock:
            for fmt in FORMATS:
                self._data[fmt] = {**found[fmt], **self._data[fmt]}
            self.ready = True
            self._save()
        n = sum(len(v) for v in found.values())
        log.info("Library registry bootstrap: %d audio + %d video songs from %d files in %.1f s",
                 len(found["audio"]), len(found["video"]), len(files), time.monotonic() - started)
        return n


def embedded_id(path: str | Path) -> str | None:
    """YouTube video id from the URL yt-dlp's FFmpegMetadata embeds: ID3 TXXX:purl/comment, MP4 ©cmt."""
    path = Path(path)
    try:
        if path.suffix.lower() == ".mp3":
            urls = [text for frame in ID3(path).getall("TXXX") if frame.desc in ("purl", "comment")
                    for text in frame.text]
        else:
            urls = list((MP4(path).tags or {}).get("\xa9cmt", []))
    except Exception:  # noqa: BLE001 — a corrupt or tagless file is just not identified
        return None
    return next((vid for u in urls if isinstance(u, str) and is_youtube(u) and (vid := video_id(u))), None)


def bootstrap_roots(outdir: str | Path, home: Path | None = None) -> list[Path]:
    """Folders to scan on the first run: the output folder, ~/Music, and every folder with a legacy archive
    under the output folder or among its parents up to the home dir (never the whole disk)."""
    home = home or Path.home()
    out = Path(outdir).expanduser()
    roots = {d for d in (out, home / "Music") if d.is_dir()}
    if out.is_dir():
        roots |= {p.parent for name in LEGACY_ARCHIVES for p in out.rglob(name)}
        for d in out.parents:
            if d != home and home not in d.parents:
                break
            roots |= {d for name in LEGACY_ARCHIVES if (d / name).is_file()}
    # A root inside another root is scanned with it.
    return sorted(r for r in roots if not any(o in r.parents for o in roots))


def recording(download: Callable, registry: "Registry") -> Callable:
    """Wrap downloader.download (as BatchRunner calls it) so every real download is recorded."""
    def run(track, outdir, quality="192", subfolder="", on_progress=None, cancel_event=None, fmt="audio"):
        path = download(track, outdir, quality, subfolder, on_progress, cancel_event, fmt)
        if path:
            registry.record(fmt, track.id, path)
        return path
    return run


REGISTRY = Registry(user_config_dir() / "library.json")
