from pathlib import Path

from youtube_download.core.system import clipboard_commands, default_outdir


def which_of(*present):
    return lambda name: f"/bin/{name}" if name in present else None


def test_clipboard_macos():
    assert clipboard_commands("darwin", which_of("pbpaste")) == [["pbpaste"]]


def test_clipboard_windows():
    assert clipboard_commands("win32", which_of("powershell")) == [
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]
    ]


def test_clipboard_linux_order_and_only_installed():
    assert clipboard_commands("linux", which_of("wl-paste", "xclip", "xsel")) == [
        ["wl-paste", "--no-newline"],
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "-b"],
    ]
    assert clipboard_commands("linux", which_of("xsel")) == [["xsel", "-b"]]
    assert clipboard_commands("linux", which_of()) == []


def test_default_outdir_prefers_music_then_downloads_then_home(tmp_path):
    assert default_outdir(tmp_path) == tmp_path
    (tmp_path / "Downloads").mkdir()
    assert default_outdir(tmp_path) == tmp_path / "Downloads"
    (tmp_path / "Music").mkdir()
    assert default_outdir(tmp_path) == tmp_path / "Music"
