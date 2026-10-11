from mutagen.id3 import APIC, ID3

from pista.core.library import cover_bytes, scan


def test_cover_bytes_reads_embedded_picture(tmp_path):
    mp3 = tmp_path / "a.mp3"
    tags = ID3()
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=b"\xff\xd8jpegdata"))
    tags.save(mp3)
    assert cover_bytes(mp3) == (b"\xff\xd8jpegdata", "image/jpeg")


def test_cover_bytes_none_without_picture_or_tags(tmp_path):
    plain = tmp_path / "b.mp3"
    plain.write_bytes(b"")
    assert cover_bytes(plain) is None
    assert cover_bytes(tmp_path / "missing.mp3") is None


def test_scan_includes_mp4(tmp_path):
    for n in ("a.mp3", "b.mp4", "c.webm"):
        (tmp_path / n).write_bytes(b"")
    assert [p.name for p in scan(tmp_path)] == ["a.mp3", "b.mp4"]
