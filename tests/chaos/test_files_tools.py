"""5/6/7/8/9: hostile filesystem, corrupt media and missing/hanging tools."""
import os
import stat
import sys
import time

import pytest

import pista.core.system as system
from pista.core.downloader import base_opts, target_dir
from pista.core.library import cover_bytes, scan
from pista.core.plan import archived_ids

posix_only = pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions")


def test_archive_missing_or_a_directory(tmp_path):
    assert archived_ids(tmp_path / "missing.txt") == set()
    (tmp_path / "dir.txt").mkdir()
    assert archived_ids(tmp_path / "dir.txt") == set()


@posix_only
def test_archive_unreadable(tmp_path):
    p = tmp_path / ".downloaded-audio.txt"
    p.write_text("youtube AAAAAAAAAAA\n")
    p.chmod(0)
    try:
        assert archived_ids(p) == set()
    finally:
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_output_folder_is_a_file(tmp_path):
    f = tmp_path / "Music"
    f.write_text("not a folder")
    assert target_dir(f, "") == f  # downloading there then fails as an item error, not a crash
    assert archived_ids(f / ".downloaded-audio.txt") == set()


def test_library_tolerates_junk_media(tmp_path):
    (tmp_path / "zero.mp3").write_bytes(b"")
    (tmp_path / "text.mp3").write_text("I am not an mp3")
    (tmp_path / "badtag.mp3").write_bytes(b"ID3\x04\x00\x00\x7f\x7f\x7f\x7fgarbage" * 50)
    (tmp_path / "zero.mp4").write_bytes(b"")
    (tmp_path / "broken.mp3").symlink_to(tmp_path / "nowhere.mp3")
    files = scan(tmp_path)
    assert [p.name for p in files] == ["badtag.mp3", "text.mp3", "zero.mp3", "zero.mp4"]
    assert all(cover_bytes(p) is None for p in files)


@posix_only
def test_library_skips_unreadable_subfolders(tmp_path):
    (tmp_path / "ok.mp3").write_bytes(b"")
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "x.mp3").write_bytes(b"")
    locked.chmod(0)
    try:
        assert [p.name for p in scan(tmp_path)] == ["ok.mp3"]
    finally:
        locked.chmod(stat.S_IRWXU)


def test_missing_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(system, "_search_dirs", lambda: [])
    monkeypatch.setenv("PATH", str(tmp_path))  # nothing on PATH
    system.find_ffmpeg.cache_clear(); system.find_deno.cache_clear()
    try:
        assert system.find_ffmpeg() is None and not system.has_ffmpeg() and system.find_deno() is None
        opts = base_opts(system.find_ffmpeg(), system.find_deno(), None)
        assert "ffmpeg_location" not in opts and "js_runtimes" not in opts  # yt-dlp defaults, no crash
    finally:
        system.find_ffmpeg.cache_clear(); system.find_deno.cache_clear()


def test_clipboard_missing_or_failing(monkeypatch):
    monkeypatch.setattr(system, "clipboard_commands", lambda: [])
    assert system.read_clipboard() is None
    monkeypatch.setattr(system, "clipboard_commands", lambda: [["false"], ["/nonexistent/pbpaste"]])
    assert system.read_clipboard() is None


@pytest.mark.skipif(sys.platform == "win32", reason="uses sleep(1)")
def test_clipboard_hang_times_out(monkeypatch):
    monkeypatch.setattr(system, "clipboard_commands", lambda: [["sleep", "30"]])
    t0 = time.monotonic()
    assert system.read_clipboard() is None
    assert time.monotonic() - t0 < 5  # bounded by the 3 s timeout


def test_partial_downloads_stay_resumable():
    opts = base_opts(None, None, None)
    assert opts.get("continuedl", True) is not False and not opts.get("nopart")
