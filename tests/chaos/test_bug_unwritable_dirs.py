import logging
import os
import stat
import sys

import pytest

posix_only = pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions")


@posix_only
def test_unwritable_log_dir_falls_back_instead_of_crashing(tmp_path):
    from pista.core.applog import setup_logging

    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        path = setup_logging(locked / "logs")  # used to raise PermissionError → blank app window
        logging.getLogger("pista").warning("still logging")
        assert path is not None and "locked" not in str(path)
    finally:
        locked.chmod(stat.S_IRWXU)


def test_log_file_that_is_a_directory(tmp_path):
    from pista.core.applog import LOG_NAME, setup_logging

    (tmp_path / LOG_NAME).mkdir()
    assert setup_logging(tmp_path) != tmp_path / LOG_NAME


@posix_only
def test_unwritable_cache_dir_does_not_break_preview_dir(tmp_path, monkeypatch):
    from pista.core import system

    locked = tmp_path / "cache"
    locked.mkdir()
    locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
    monkeypatch.setattr(system, "user_cache_dir", lambda *a, **k: locked / "pista")
    try:
        d = system.writable_dir("previews")
        assert d.is_dir() and os.access(d, os.W_OK)
    finally:
        locked.chmod(stat.S_IRWXU)
