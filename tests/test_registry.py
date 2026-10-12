import json
import shutil
import subprocess
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TXXX

from pista.core.models import Track
from pista.core.registry import Registry, bootstrap_roots, embedded_id, recording

FFMPEG = shutil.which("ffmpeg")


def mp3_with_url(path: Path, url: str, desc: str = "purl") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    tags = ID3()
    tags.add(TXXX(encoding=3, desc=desc, text=url))
    tags.save(path)
    return path


def test_record_path_for_and_existing(tmp_path):
    reg = Registry(tmp_path / "library.json")
    song = tmp_path / "a.mp3"
    song.write_bytes(b"x")
    reg.record("audio", "AAAAAAAAAAA", song)
    reg.record("audio", "BBBBBBBBBBB", tmp_path / "gone.mp3")  # recorded, then deleted/moved
    assert reg.path_for("audio", "AAAAAAAAAAA") == song
    assert reg.path_for("video", "AAAAAAAAAAA") is None
    assert reg.existing("audio", ["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"]) == {"AAAAAAAAAAA"}
    assert reg.existing("video", ["AAAAAAAAAAA"]) == set()


def test_saved_atomically_and_reloaded(tmp_path):
    path = tmp_path / "cfg" / "library.json"
    reg = Registry(path)
    reg.ready = True
    reg.record("video", "AAAAAAAAAAA", tmp_path / "v.mp4")
    assert json.loads(path.read_text("utf-8")) == {"audio": {}, "video": {"AAAAAAAAAAA": str(tmp_path / "v.mp4")}}
    assert not list(path.parent.glob("*.tmp"))  # temp file replaced, not left behind
    assert Registry(path).path_for("video", "AAAAAAAAAAA") == tmp_path / "v.mp4"


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '{"audio": [1]}', '{"audio": {"x": 3}}'])
def test_corrupt_file_loads_empty(tmp_path, content):
    path = tmp_path / "library.json"
    path.write_text(content, "utf-8")
    reg = Registry(path)
    assert reg.ready  # a file exists: no bootstrap
    assert reg.path_for("audio", "x") is None


def test_missing_file_is_not_ready_and_records_stay_in_memory(tmp_path):
    path = tmp_path / "library.json"
    reg = Registry(path)
    assert not reg.ready
    reg.record("audio", "AAAAAAAAAAA", tmp_path / "a.mp3")
    assert not path.exists()  # written by bootstrap, so an interrupted bootstrap reruns next start


def test_embedded_id_reads_purl_or_comment(tmp_path):
    a = mp3_with_url(tmp_path / "a.mp3", "https://www.youtube.com/watch?v=Wz84N4A6S6Q")
    b = mp3_with_url(tmp_path / "b.mp3", "https://youtu.be/CHFNFHJG0AI", desc="comment")
    c = mp3_with_url(tmp_path / "c.mp3", "https://example.com/watch?v=XXXXXXXXXXX")
    (tmp_path / "junk.mp3").write_text("not an mp3")
    assert embedded_id(a) == "Wz84N4A6S6Q"
    assert embedded_id(b) == "CHFNFHJG0AI"
    assert embedded_id(c) is None
    assert embedded_id(tmp_path / "junk.mp3") is None


@pytest.mark.skipif(not FFMPEG, reason="needs ffmpeg to create test media")
def test_embedded_id_reads_mp4_comment(tmp_path):
    # What yt-dlp's FFmpegMetadata writes: purl+comment; the MP4 muxer keeps only `comment` (©cmt).
    mp4 = tmp_path / "v.mp4"
    url = "https://www.youtube.com/watch?v=Wz84N4A6S6Q"
    subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", "-c:a", "aac",
                    "-metadata", f"purl={url}", "-metadata", f"comment={url}", str(mp4)], check=True)
    assert embedded_id(mp4) == "Wz84N4A6S6Q"


def test_bootstrap_maps_ids_to_paths_and_saves(tmp_path):
    lib = tmp_path / "Music"
    a = mp3_with_url(lib / "Peso Pluma" / "a.mp3", "https://www.youtube.com/watch?v=AAAAAAAAAAA")
    b = mp3_with_url(lib / "Tito" / "b.mp3", "https://www.youtube.com/watch?v=BBBBBBBBBBB")
    reg = Registry(tmp_path / "library.json")
    reg.record("audio", "BBBBBBBBBBB", lib / "newer.mp3")  # recorded meanwhile: wins over the scan
    assert reg.bootstrap([lib, lib / "Tito"]) == 2
    assert reg.ready and (tmp_path / "library.json").exists()
    assert reg.path_for("audio", "AAAAAAAAAAA") == a
    assert reg.path_for("audio", "BBBBBBBBBBB") == lib / "newer.mp3"
    assert b.exists()


def test_bootstrap_roots(tmp_path):
    home = tmp_path / "home"
    out = home / "Music" / "new music"
    (out / "Peso Pluma").mkdir(parents=True)
    (out / "Peso Pluma" / ".downloaded-audio.txt").write_text("")
    (home / "Music" / ".downloaded.txt").write_text("")
    (home / "Other").mkdir()
    (home / "Other" / ".downloaded-video.txt").write_text("")  # not under out nor a parent: ignored
    roots = bootstrap_roots(out, home)
    assert set(roots) == {home / "Music"}  # out and its subfolder are inside ~/Music already


def test_bootstrap_roots_outside_home(tmp_path):
    out = tmp_path / "ext"
    out.mkdir()
    assert bootstrap_roots(out, tmp_path / "home") == [out]


def test_recording_wraps_download(tmp_path):
    reg = Registry(tmp_path / "library.json")
    t = Track("AAAAAAAAAAA", "t", "c", 1, "https://www.youtube.com/watch?v=AAAAAAAAAAA", None)
    run = recording(lambda *a: str(tmp_path / "t.mp3"), reg)
    assert run(t, "/o", "192", "", None, None, "audio") == str(tmp_path / "t.mp3")
    assert reg.path_for("audio", t.id) == tmp_path / "t.mp3"
    skipped = recording(lambda *a: None, reg)
    assert skipped(t, "/o", "192", "", None, None, "video") is None
    assert reg.path_for("video", t.id) is None
