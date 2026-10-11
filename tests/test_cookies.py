"""Optional «use my browser's YouTube session» (cookiesfrombrowser). Off by default; only the choice is stored."""
import json
import logging
import os
import sys
from pathlib import Path

import pytest
from yt_dlp.cookies import SUPPORTED_BROWSERS

import pista.core.downloader as dl
from pista.core.applog import setup_logging
from pista.core.batch import friendly_error
from pista.core.settings import DEFAULTS, browsers_for, load_settings, save_settings
from pista.core.system import user_config_dir

BOT_HINT = "Puedes activar «Usar la sesión de YouTube de mi navegador» en las opciones."


def test_base_opts_only_include_cookies_when_enabled():
    assert "cookiesfrombrowser" not in dl.base_opts(None, None, None)
    assert dl.base_opts(None, None, None, cookies_browser="firefox")["cookiesfrombrowser"] == ("firefox",)


def test_every_yt_dlp_call_uses_the_current_choice(monkeypatch):
    seen = []
    monkeypatch.setattr(dl.yt_dlp, "YoutubeDL", lambda opts: seen.append(opts) or opts)
    dl.set_cookie_browser(None)
    dl._ydl({})
    dl.set_cookie_browser("firefox")
    dl._ydl({})
    dl.set_cookie_browser(None)
    assert "cookiesfrombrowser" not in seen[0] and seen[1]["cookiesfrombrowser"] == ("firefox",)


@pytest.mark.parametrize("platform, has_safari", [("darwin", True), ("win32", False), ("linux", False)])
def test_browsers_for_platform(platform, has_safari):
    names = [k for k, _ in browsers_for(platform)]
    assert set(names) <= SUPPORTED_BROWSERS and ("safari" in names) is has_safari
    assert names[0] in ("firefox", "chrome")


def test_settings_default_off_and_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    assert load_settings(p) == DEFAULTS and DEFAULTS["cookies"] is False
    save_settings(p, {"cookies": True, "browser": "firefox"})
    assert load_settings(p) == {"cookies": True, "browser": "firefox"}
    assert set(json.loads(p.read_text("utf-8"))) == {"cookies", "browser"}  # only the choice is stored


@pytest.mark.parametrize("content", [b"{not json", b"\xff\xfe\x00", b"[]", b'{"cookies": "yes", "browser": 5}',
                                     b'{"cookies": true, "browser": "netscape"}'])
def test_settings_tolerate_corruption(tmp_path, content):
    p = tmp_path / "settings.json"
    p.write_bytes(content)
    s = load_settings(p)
    assert isinstance(s["cookies"], bool) and s["browser"] in SUPPORTED_BROWSERS


def test_save_settings_failure_does_not_raise(tmp_path):
    save_settings(tmp_path / "missing-dir" / "x" / "settings.json", {"cookies": True, "browser": "firefox"})
    save_settings(tmp_path, {"cookies": True, "browser": "firefox"})  # a directory: ignored


def test_user_config_dir_per_os(tmp_path):
    h = tmp_path
    assert user_config_dir("darwin", {}, h) == h / "Library" / "Application Support" / "pista"
    assert user_config_dir("win32", {"APPDATA": str(h / "R")}, h) == h / "R" / "pista"
    assert user_config_dir("linux", {"XDG_CONFIG_HOME": str(h / "c")}, h) == h / "c" / "pista"
    assert user_config_dir("linux", {}, h) == h / ".config" / "pista"


def test_log_never_contains_cookie_values(tmp_path):
    path = setup_logging(tmp_path)
    log = logging.getLogger("pista.yt_dlp")
    log.warning("Cookie: SID=abc123; HSID=def456; __Secure-3PSID=ghi789")
    log.warning("[debug] Set-Cookie: LOGIN_INFO=AFmmF2swRQIh; Path=/")
    log.warning("headers {'Cookie': 'VISITOR_INFO1_LIVE=xyz; PREF=f6=40000000'}")
    log.info("Extracted 42 cookies from firefox")
    for h in logging.getLogger("pista").handlers:
        h.flush()
    text = Path(path).read_text("utf-8")
    for secret in ("abc123", "def456", "ghi789", "AFmmF2swRQIh", "xyz", "f6=40000000"):
        assert secret not in text
    assert "Extracted 42 cookies from firefox" in text


@pytest.mark.parametrize("raw, expected_start", [
    ("ERROR: Failed to decrypt with DPAPI. See  https://github.com/yt-dlp/yt-dlp/issues/10927  for more info",
     "No se pudieron leer las cookies de ese navegador en Windows"),
    ("ERROR: Could not copy Chrome cookie database. See  https://github.com/yt-dlp/yt-dlp/issues/7271  for more info",
     "El navegador tiene sus cookies bloqueadas"),
    ("PermissionError: [Errno 1] Operation not permitted: '/Users/x/Library/Cookies/Cookies.binarycookies'",
     "Para usar Safari, da a Pista «Acceso total al disco»"),
    ("could not find firefox cookies database in /home/x/.mozilla/firefox", "No se encontró el perfil de ese navegador"),
    ("ERROR: failed to load cookies", "No se pudieron leer las cookies del navegador"),
])
def test_cookie_errors_are_explained(raw, expected_start):
    assert friendly_error(raw).startswith(expected_start)


def test_bot_check_suggests_the_option():
    msg = friendly_error("ERROR: [youtube] x: Sign in to confirm you’re not a bot.")
    assert msg.endswith(BOT_HINT)


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0,
                    reason="chmod can't make a folder unreadable on Windows or for root")
def test_blocked_browser_folder_asks_for_disk_access(tmp_path):
    profile = tmp_path / "Brave-Browser"
    profile.mkdir()
    profile.chmod(0)  # what macOS privacy protection looks like to yt-dlp: the folder exists but can't be read
    try:
        msg = friendly_error(f'ERROR: could not find brave cookies database in "{profile}"')
    finally:
        profile.chmod(0o700)
    assert "Acceso total al disco" in msg
