"""Reproductor: metadata from tags, fallbacks, format groups, counts, sorting and prev/next order."""
import random
import time
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TIT2, TPE1
from mutagen.mp4 import MP4

from pista.core.library import Entry, MetaCache, counts, entry_for, library_view, load_library, next_entry, visible

import shutil

FFMPEG = Path(shutil.which("ffmpeg") or Path(__file__).resolve().parents[1] / "build" / "ffmpeg" / "ffmpeg")


def e(name, fmt="MP3", title=None, artist="—", duration=None):
    return Entry(Path(f"/m/{name}"), fmt, title or name, artist, duration)


def test_fallback_order_never_uses_the_folder_name():
    p = Path("/Users/x/Music/Some Mix/Artist A - Song B.mp3")
    assert entry_for(p, ("Tag Title", "Tag Artist", 61.4)) == Entry(p, "MP3", "Tag Title", "Tag Artist", 61.4)
    assert entry_for(p, (None, None, None)) == Entry(p, "MP3", "Song B", "Artist A", None)
    q = Path("/Users/x/Music/Me at the zoo.mp4")
    assert entry_for(q, (None, None, 19.0)) == Entry(q, "MP4", "Me at the zoo", "—", 19.0)
    assert entry_for(q, ("", "  ", None)).artist == "—"


def test_counts_respect_search():
    es = [e("a.mp3", artist="Zed"), e("b.mp3"), e("c.mp4", "MP4", artist="Zed")]
    assert counts(es, "") == {"all": 3, "mp3": 2, "mp4": 1}
    assert counts(es, "zed") == {"all": 2, "mp3": 1, "mp4": 1}


def test_all_mode_groups_mp3_first_and_filters():
    es = [e("x.mp4", "MP4"), e("b.mp3"), e("a.mp3")]
    assert [(h, [x.title for x in rows]) for h, rows in library_view(es, "", "all")] == \
        [("MP3 · 2", ["a.mp3", "b.mp3"]), ("MP4 · 1", ["x.mp4"])]
    assert [(h, [x.title for x in rows]) for h, rows in library_view(es, "", "mp4")] == [(None, ["x.mp4"])]
    assert library_view(es, "nothing", "all") == []


def test_sorting_within_groups():
    es = [e("1.mp3", title="B", artist="y", duration=30), e("2.mp3", title="a", artist="z", duration=None),
          e("3.mp3", title="C", artist="x", duration=10)]
    titles = lambda **kw: [x.title for _, rows in library_view(es, "", "mp3", **kw) for x in rows]  # noqa: E731
    assert titles(sort="title") == ["a", "B", "C"]
    assert titles(sort="title", desc=True) == ["C", "B", "a"]
    assert titles(sort="artist") == ["C", "B", "a"]
    assert titles(sort="duration") == ["C", "B", "a"]  # unknown durations last


def test_next_moves_within_the_visible_list_even_if_current_is_hidden():
    es = [e("a.mp3"), e("b.mp4", "MP4"), e("c.mp3"), e("d.mp4", "MP4")]
    vis = visible(library_view(es, "", "mp3"))
    assert [x.title for x in vis] == ["a.mp3", "c.mp3"]
    assert next_entry(vis, es[0].path, 1).title == "c.mp3"
    assert next_entry(vis, es[2].path, 1).title == "a.mp3"  # wraps
    assert next_entry(vis, es[0].path, -1).title == "c.mp3"
    assert next_entry(vis, es[1].path, 1).title == "a.mp3"  # playing an MP4 that is filtered out
    assert next_entry(vis, None, 1).title == "a.mp3"
    assert next_entry([], es[0].path, 1) is None
    assert next_entry(vis, es[0].path, 1, shuffle=True, rng=random.Random(1)).fmt == "MP3"


def test_tags_are_read_from_real_files(tmp_path):
    mp3 = tmp_path / "file name.mp3"
    mp3.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Real Title"))
    tags.add(TPE1(encoding=3, text="Real Artist"))
    tags.save(mp3)
    (es,) = [load_library(tmp_path, MetaCache())]
    assert (es[0].title, es[0].artist) == ("Real Title", "Real Artist")


@pytest.mark.skipif(not FFMPEG.exists(), reason="needs ffmpeg to create test media")
def test_durations_and_mp4_tags(tmp_path):
    import subprocess
    mp3, mp4 = tmp_path / "a.mp3", tmp_path / "b.mp4"
    subprocess.run([str(FFMPEG), "-v", "error", "-f", "lavfi", "-i", "sine=d=3", "-q:a", "9", str(mp3)], check=True)
    subprocess.run([str(FFMPEG), "-v", "error", "-f", "lavfi", "-i", "sine=d=2", "-c:a", "aac", str(mp4)], check=True)
    m = MP4(mp4)
    m["\xa9nam"], m["\xa9ART"] = ["Video Title"], ["Video Artist"]
    m.save()
    es = {x.path.name: x for x in load_library(tmp_path, MetaCache())}
    assert round(es["a.mp3"].duration) == 3 and round(es["b.mp4"].duration) == 2
    assert (es["b.mp4"].title, es["b.mp4"].artist) == ("Video Title", "Video Artist")


def test_cache_skips_unchanged_files(tmp_path, monkeypatch):
    for i in range(3):
        (tmp_path / f"Art - T{i}.mp3").write_bytes(b"")
    cache = MetaCache()
    load_library(tmp_path, cache)
    import pista.core.library as lib
    calls = []
    monkeypatch.setattr(lib, "read_meta", lambda p: calls.append(p) or (None, None, None))
    load_library(tmp_path, cache)
    assert calls == []
    time.sleep(0.01)
    (tmp_path / "Art - T0.mp3").write_bytes(b"changed")
    load_library(tmp_path, cache)
    assert [p.name for p in calls] == ["Art - T0.mp3"]
