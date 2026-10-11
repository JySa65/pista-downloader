from pista.core.plan import archived_ids


def test_binary_or_garbage_archive_is_tolerated(tmp_path):
    p = tmp_path / ".downloaded-audio.txt"
    p.write_bytes(b"\xff\xfe\x00garbage\x80\x81\nyoutube AAAAAAAAAAA\nnot a line\n\x00\x00\n")
    assert archived_ids(p) == {"AAAAAAAAAAA"}


def test_corrupt_archive_is_repaired_before_yt_dlp_reads_it(tmp_path):
    import yt_dlp

    from pista.core.downloader import repair_archive

    p = tmp_path / ".downloaded-audio.txt"
    p.write_bytes(b"\xff\xfe\x00garbage\x80\nyoutube AAAAAAAAAAA\nyoutube BBBBBBBBBBB\n")
    backup = repair_archive(p)
    assert backup is not None and backup.exists() and backup.read_bytes().startswith(b"\xff\xfe")
    assert p.read_text("utf-8").splitlines() == ["youtube AAAAAAAAAAA", "youtube BBBBBBBBBBB"]
    ydl = yt_dlp.YoutubeDL({"download_archive": str(p), "quiet": True})  # used to raise UnicodeDecodeError
    assert "youtube aaaaaaaaaaa" in {x.lower() for x in ydl.archive}


def test_valid_or_missing_archive_is_left_alone(tmp_path):
    from pista.core.downloader import repair_archive

    p = tmp_path / ".downloaded-audio.txt"
    assert repair_archive(p) is None and not p.exists()
    p.write_text("youtube AAAAAAAAAAA\n", "utf-8")
    assert repair_archive(p) is None and p.read_text("utf-8") == "youtube AAAAAAAAAAA\n"
