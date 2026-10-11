import logging
from urllib.parse import parse_qs, urlparse

from pista.core.applog import redact, setup_logging
from pista.core.report import REPO, issue_url, os_label


def test_redact_home_posix():
    assert redact("saved /Users/ana/Music/x.mp3 and /Users/ana", "/Users/ana", "darwin") == "saved ~/Music/x.mp3 and ~"
    assert redact("/home/anabel/x", "/home/ana", "linux") == "/home/anabel/x"  # not a path prefix of another user
    assert redact("/Users/Ana/x", "/Users/ana", "darwin") == "/Users/Ana/x"  # case-sensitive off Windows


def test_redact_home_windows_case_insensitive_both_slashes():
    home = r"C:\Users\Ana"
    text = r"C:\users\ana\Music\a.mp3 | c:/Users/ANA/Downloads | C:\Users\Anabel\x"
    assert redact(text, home, "win32") == r"~\Music\a.mp3 | ~/Downloads | C:\Users\Anabel\x"


def test_log_file_is_anonymized(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home" / "ana"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home" / "ana"))  # Path.home() on Windows
    path = setup_logging(tmp_path / "logs")
    logging.getLogger("pista").info("✓ %s/Music/song.mp3", str(tmp_path / "home" / "ana"))
    for h in logging.getLogger("pista").handlers:
        h.flush()
    text = path.read_text("utf-8")
    assert "✓ ~/Music/song.mp3" in text and "home/ana" not in text


def test_os_label():
    assert os_label("Windows", "10", "10.0.19045") == "Windows 10 (10.0.19045)"
    assert os_label("Windows", "10", "10.0.22631") == "Windows 11 (10.0.22631)"
    assert os_label("Darwin", "24.6.0", "", mac_ver="15.6") == "macOS 15.6"
    assert os_label("Linux", "6.8.0-45-generic", "#45-Ubuntu") == "Linux 6.8.0-45-generic"


def test_issue_url_prefills_form_fields():
    url = issue_url("0.2.1", "Windows 11 (10.0.22631)")
    u = urlparse(url)
    assert f"{u.scheme}://{u.netloc}{u.path}" == f"https://github.com/{REPO}/issues/new"
    q = parse_qs(u.query)
    assert q == {"template": ["bug_report.yml"], "version": ["0.2.1"], "os_version": ["Windows 11 (10.0.22631)"]}


def test_issue_url_fields_exist_in_bug_form():
    import yaml
    from pathlib import Path

    form = yaml.safe_load((Path(__file__).parent.parent / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text("utf-8"))
    ids = {item.get("id") for item in form["body"]}
    q = parse_qs(urlparse(issue_url("1.0.0", "macOS 15")).query)
    assert set(q) - {"template"} <= ids
    log_field = next(i for i in form["body"] if i.get("id") == "log")
    assert log_field["type"] == "textarea" and "render" not in log_field["attributes"]  # allows attachments
    assert log_field["validations"]["required"] is False
