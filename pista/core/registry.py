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

from .plan import archived_ids
from .system import user_config_dir
from .urls import is_youtube, video_id

log = logging.getLogger("pista.registry")

FORMATS = ("audio", "video")
EXT_FORMAT = {".mp3": "audio", ".mp4": "video"}
# yt-dlp's per-folder download archives written by earlier versions; they mark folders worth scanning.
LEGACY_ARCHIVES = (".downloaded-audio.txt", ".downloaded-video.txt", ".downloaded.txt")
MAX_SCAN_FILES = 20_000  # first-run scan budget (paths walked), so a huge folder can't stall it


class Registry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()  # downloads record from worker threads
        # `bootstrapped` is persisted: until the first-run scan has completed once, callers fall back to the
        # legacy archives and the scan runs again on the next start. Records are saved either way.
        # `ready` is in memory only: also set when a failed scan is given up for this run.
        self._bootstrapped, self._data = self._load()
        self.ready = self._bootstrapped

    def _load(self) -> tuple[bool, dict[str, dict[str, str]]]:
        """Valid entries of the saved file; an unreadable one is set aside and treated as no registry yet."""
        data: dict[str, dict[str, str]] = {fmt: {} for fmt in FORMATS}
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except FileNotFoundError:
            return False, data
        except OSError:
            log.warning("Could not read the library registry at %s", self.path, exc_info=True)
            return False, data
        except ValueError:
            raw = None
        if not isinstance(raw, dict):
            aside = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
            log.warning("Corrupt library registry at %s, moved to %s; rebuilding it", self.path, aside.name)
            try:
                os.replace(self.path, aside)
            except OSError:
                log.warning("Could not move the corrupt library registry aside", exc_info=True)
            return False, data
        for fmt in FORMATS:
            entries = raw.get(fmt)
            if isinstance(entries, dict):
                data[fmt] = {k: v for k, v in entries.items() if isinstance(k, str) and isinstance(v, str)}
        return raw.get("bootstrapped") is True, data

    def _save(self) -> None:
        """Atomic, best effort (caller holds the lock): a registry that can't be written never breaks a download."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps({"bootstrapped": self._bootstrapped, **self._data}, ensure_ascii=False),
                           "utf-8")
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

    def bootstrap(self, roots: Iterable[str | Path], max_files: int = MAX_SCAN_FILES) -> int:
        """Scan MP3/MP4 files under `roots` for their embedded YouTube URL; record them, mark ready and save.

        Returns how many files were identified. Ids recorded meanwhile (live downloads) win over the scan.
        """
        started = time.monotonic()
        found: dict[str, dict[str, str]] = {fmt: {} for fmt in FORMATS}
        files = _media_files(roots, max_files)
        for f in sorted(files):
            vid = embedded_id(f)
            if vid:
                found[EXT_FORMAT[f.suffix.lower()]].setdefault(vid, str(f))
        with self._lock:
            for fmt in FORMATS:
                self._data[fmt] = {**found[fmt], **self._data[fmt]}
            self.ready = self._bootstrapped = True
            self._save()
        n = sum(len(v) for v in found.values())
        log.info("Library registry bootstrap: %d audio + %d video songs from %d files in %.1f s",
                 len(found["audio"]), len(found["video"]), len(files), time.monotonic() - started)
        return n


def _media_files(roots: Iterable[str | Path], max_files: int) -> set[Path]:
    """MP3/MP4 files under `roots`, walking at most `max_files` paths in total."""
    files: set[Path] = set()
    walked = 0
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            walked += 1
            if walked > max_files:
                log.warning("Library registry bootstrap hit the scan cap (%d files); the rest is not imported",
                            max_files)
                return files
            if p.suffix.lower() in EXT_FORMAT and p.is_file():
                files.add(p)
    return files


def existing_ids(registry: "Registry", fmt: str, ids: Iterable[str], legacy_archive: str | Path) -> set[str]:
    """The ids that already exist: in the registry, plus the output folder's legacy archive where it's trusted.

    The legacy archive (ids only, no paths) counts until the first-run scan ends, and always for video: Pista's
    MP4s carry no embedded URL, so the scan can't import them. For audio it still counts for ids the registry
    doesn't know (the scan is bounded and may miss folders); an id the registry knows is decided by its path,
    so a deleted file is downloaded again.
    """
    ids = set(ids)
    found = registry.existing(fmt, ids)
    legacy = archived_ids(legacy_archive) & ids
    if fmt == "video" or not registry.ready:
        found |= legacy
    else:
        found |= {vid for vid in legacy if registry.path_for(fmt, vid) is None}
    return found


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
    under the output folder or among its parents up to the home dir (never the whole disk).

    The home dir, its parents and volume roots are never roots: if the output folder is one of them, only its
    subfolders (two levels deep) that hold a legacy archive are scanned.
    """
    home = home or Path.home()
    out = Path(outdir).expanduser()

    def broad(d: Path) -> bool:
        return d == home or d in home.parents or d.parent == d or os.path.ismount(d)

    roots = {d for d in (out, home / "Music") if d.is_dir()}
    if out.is_dir():
        if broad(out):
            roots |= {p.parent for name in LEGACY_ARCHIVES for pat in ("*/", "*/*/") for p in out.glob(pat + name)}
        else:
            roots |= {p.parent for name in LEGACY_ARCHIVES for p in out.rglob(name)}
        for d in out.parents:
            if d != home and home not in d.parents:
                break
            roots |= {d for name in LEGACY_ARCHIVES if (d / name).is_file()}
    roots = {r for r in roots if not broad(r)}
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
