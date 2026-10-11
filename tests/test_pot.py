"""PO Token provider (bgutil script mode): server lookup, yt-dlp options, log noise."""
import logging

from pista.core.downloader import _Logger, base_opts
from pista.core.system import pot_server_dir

_HTTP_PING = ("[pot:bgutil:http] Error reaching GET http://127.0.0.1:4416/ping (caused by TransportError). "
              "This is expected if you are using the script method.")


def _server(root):
    s = root / "bgutil-server"
    (s / "src").mkdir(parents=True)
    (s / "src" / "generate_once.ts").write_text("")
    (s / "VERSION").write_text("2.0.2\n")  # written last by fetch_pot_server.py: the fetch completed
    return s


def test_pot_server_found_in_first_dir_that_has_the_script(tmp_path):
    empty, bundled = tmp_path / "a", tmp_path / "b"
    (empty / "bgutil-server").mkdir(parents=True)  # no src/generate_once.ts: incomplete, skipped
    server = _server(bundled)
    assert pot_server_dir([empty, bundled]) == server


def test_no_pot_server_when_missing(tmp_path):
    assert pot_server_dir([tmp_path, tmp_path / "missing"]) is None


def test_base_opts_points_bgutil_at_the_server():
    opts = base_opts(ffmpeg=None, deno="/d/deno", logger=None, pot_server="/srv/bgutil")
    assert opts["extractor_args"]["youtubepot-bgutilscript"] == {"server_home": ["/srv/bgutil"]}
    # yt-dlp's default clients never ask for a PO token; mweb does, and gets one from bgutil.
    assert opts["extractor_args"]["youtube"] == {"player_client": ["default", "mweb"]}


def test_base_opts_without_deno_or_server_skips_bgutil():
    assert "extractor_args" not in base_opts(ffmpeg=None, deno=None, logger=None, pot_server="/srv/bgutil")
    assert "extractor_args" not in base_opts(ffmpeg=None, deno="/d/deno", logger=None)


def test_logger_hides_expected_http_ping_error(caplog):
    caplog.set_level(logging.DEBUG, logger="pista.yt_dlp")
    for emit in (_Logger().debug, _Logger().info, _Logger().warning):
        emit(_HTTP_PING)
    assert [r.levelno for r in caplog.records] == [logging.DEBUG] * 3


def test_logger_keeps_other_messages_at_their_level(caplog):
    caplog.set_level(logging.DEBUG, logger="pista.yt_dlp")
    _Logger().warning("[pot:bgutil:http] Error reaching GET /ping. Please make sure that the server is reachable")
    assert [r.levelno for r in caplog.records] == [logging.WARNING]


def test_half_fetched_pot_server_without_version_is_ignored(tmp_path):
    half, done = tmp_path / "a", tmp_path / "b"
    (_server(half) / "VERSION").unlink()  # fetch stopped before install/prune finished
    server = _server(done)
    assert pot_server_dir([half]) is None
    assert pot_server_dir([half, done]) == server


def test_failed_refetch_deactivates_the_old_server(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    import pytest
    path = Path(__file__).resolve().parents[1] / "packaging" / "fetch_pot_server.py"
    spec = importlib.util.spec_from_file_location("fetch_pot_server", path)
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)
    old = _server(tmp_path)
    (old / "VERSION").write_text("0.0.1\n")  # an older plugin's server: must be refetched
    monkeypatch.setattr(fetch, "DEST", old)
    monkeypatch.setattr(fetch, "find_deno", lambda: "/d/deno")

    def offline(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(fetch.urllib.request, "urlopen", offline)
    with pytest.raises(OSError):
        fetch.main()
    assert pot_server_dir([tmp_path]) is None
