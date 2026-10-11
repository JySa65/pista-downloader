from pista.core.plan import archived_ids


def test_binary_or_garbage_archive_is_tolerated(tmp_path):
    p = tmp_path / ".downloaded-audio.txt"
    p.write_bytes(b"\xff\xfe\x00garbage\x80\x81\nyoutube AAAAAAAAAAA\nnot a line\n\x00\x00\n")
    assert archived_ids(p) == {"AAAAAAAAAAA"}
