import json

from pista import build_date
from pista.core.updates import RELEASES_API, is_newer, parse_version, update_status


def test_parse_version():
    assert parse_version("v0.3.0") == (0, 3, 0)
    assert parse_version("1.10") == (1, 10, 0)
    assert parse_version("v2.0.0-rc.1") == (2, 0, 0)
    assert parse_version("nope") is None


def test_is_newer_semver_not_string_compare():
    assert is_newer("v0.10.0", "0.9.9")
    assert not is_newer("v0.3.0", "0.3.0")
    assert not is_newer("v0.2.9", "0.3.0")
    assert not is_newer("garbage", "0.3.0")


def test_update_status_messages():
    assert RELEASES_API == "https://api.github.com/repos/JySa65/pista-downloader/releases/latest"
    rel = {"tag_name": "v0.4.0", "html_url": "https://github.com/JySa65/pista-downloader/releases/tag/v0.4.0"}
    assert update_status(rel, "0.3.0") == ("new", "Hay una versión nueva: v0.4.0", rel["html_url"])
    assert update_status({"tag_name": "v0.3.0", "html_url": "u"}, "0.3.0") == ("latest", "Tienes la última versión.", None)
    kind, msg, url = update_status(None, "0.3.0")
    assert kind == "error" and url is None and "No se pudo comprobar" in msg


def test_build_date_from_bundle_or_dev(tmp_path):
    assert build_date(tmp_path) == "dev"
    (tmp_path / "build_info.json").write_text(json.dumps({"date": "2026.10.11"}), "utf-8")
    assert build_date(tmp_path) == "2026.10.11"
