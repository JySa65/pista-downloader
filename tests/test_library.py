from youtube_download.core.library import scan, split_artist


def test_split_artist_on_first_dash():
    assert split_artist("SAMPLE ARTIST - SAMPLE SONG (OFFICIAL VIDEO)") == ("SAMPLE ARTIST", "SAMPLE SONG (OFFICIAL VIDEO)")
    assert split_artist("A – B - C") == ("A", "B - C")


def test_split_artist_without_dash():
    assert split_artist("Me at the zoo") == ("", "Me at the zoo")


def test_scan_finds_mp3_recursively_sorted_case_insensitive(tmp_path):
    (tmp_path / "Mix - X").mkdir()
    for name in ["b.mp3", "Mix - X/a.mp3", "c.webm.part", "notes.txt"]:
        (tmp_path / name).write_bytes(b"")
    assert [p.relative_to(tmp_path).as_posix() for p in scan(tmp_path)] == ["b.mp3", "Mix - X/a.mp3"]


def test_scan_missing_folder_is_empty(tmp_path):
    assert scan(tmp_path / "nope") == []
