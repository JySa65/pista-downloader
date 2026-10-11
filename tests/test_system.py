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


# --- ffmpeg lookup and cache dir ---
from youtube_download.core.system import bundled_dirs, ffmpeg_location, user_cache_dir  # noqa: E402


def test_bundled_dirs_only_when_frozen(tmp_path):
    assert bundled_dirs(False, None, str(tmp_path / "python")) == []
    assert bundled_dirs(True, str(tmp_path / "meipass"), str(tmp_path / "app" / "YouTubeDownload")) == [
        tmp_path / "meipass" / "ffmpeg", tmp_path / "meipass", tmp_path / "app" / "ffmpeg", tmp_path / "app"
    ]


def test_ffmpeg_prefers_bundled_binary(tmp_path):
    (tmp_path / "ffmpeg").write_bytes(b"")
    assert ffmpeg_location([tmp_path], which_of("ffmpeg"), "darwin") == str(tmp_path)


def test_ffmpeg_windows_exe_name(tmp_path):
    (tmp_path / "ffmpeg.exe").write_bytes(b"")
    assert ffmpeg_location([tmp_path], which_of(), "win32") == str(tmp_path)
    assert ffmpeg_location([tmp_path], which_of(), "linux") is None


def test_ffmpeg_falls_back_to_path_then_none(tmp_path):
    assert ffmpeg_location([tmp_path], which_of("ffmpeg"), "linux") == str(Path("/bin"))
    assert ffmpeg_location([tmp_path], which_of(), "linux") is None


def test_user_cache_dir_per_os(tmp_path):
    h = tmp_path
    assert user_cache_dir("darwin", {}, h) == h / "Library" / "Caches" / "YouTubeDownload"
    assert user_cache_dir("win32", {"LOCALAPPDATA": str(h / "L")}, h) == h / "L" / "YouTubeDownload" / "Cache"
    assert user_cache_dir("win32", {}, h) == h / "AppData" / "Local" / "YouTubeDownload" / "Cache"
    assert user_cache_dir("linux", {"XDG_CACHE_HOME": str(h / "x")}, h) == h / "x" / "YouTubeDownload"
    assert user_cache_dir("linux", {}, h) == h / ".cache" / "YouTubeDownload"
