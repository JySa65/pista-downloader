from pathlib import Path

import pytest

from pista.core.downloader import target_dir


@pytest.mark.parametrize("name", ["", ".", "..", "  ", ". .", "...", "../..", "/..", "\\..", "..\\.."])
def test_unsafe_or_empty_playlist_titles_mean_no_subfolder_or_stay_inside(tmp_path, name):
    out = target_dir(tmp_path, name)
    assert out == tmp_path or tmp_path.resolve() in out.resolve().parents


def test_dot_names_are_no_subfolder(tmp_path):
    for name in ("", ".", ".."):
        assert target_dir(tmp_path, name) == tmp_path


def test_normal_title_is_a_direct_child(tmp_path):
    assert target_dir(tmp_path, "Mix - Ejemplo") == tmp_path / "Mix - Ejemplo"
    assert target_dir(tmp_path, "a/b").parent == tmp_path  # slashes are sanitized, never nested


def test_symlink_escape_is_rejected(tmp_path):
    outside = tmp_path / "outside"; outside.mkdir()
    out = tmp_path / "out"; out.mkdir()
    (out / "Lista").symlink_to(outside)
    with pytest.raises(ValueError):
        target_dir(out, "Lista")
