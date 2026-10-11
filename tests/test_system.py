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
from youtube_download.core.system import (  # noqa: E402
    bundled_dirs, ffmpeg_location, no_window, open_command, tool_path, user_cache_dir,
)


def test_bundled_dirs_only_when_frozen(tmp_path):
    assert bundled_dirs(False, None, str(tmp_path / "python")) == []
    m, a = tmp_path / "meipass", tmp_path / "app"
    assert bundled_dirs(True, str(m), str(a / "YouTubeDownload")) == [
        m / "ffmpeg", m / "deno", m, a / "ffmpeg", a / "deno", a
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


def test_tool_path_bundled_then_extra_then_path(tmp_path):
    bundled, scripts = tmp_path / "b", tmp_path / "s"
    bundled.mkdir(); scripts.mkdir()
    (scripts / "deno").write_bytes(b"")
    assert tool_path("deno", [bundled, scripts], which_of(), "darwin") == str(scripts / "deno")
    (bundled / "deno").write_bytes(b"")
    assert tool_path("deno", [bundled, scripts], which_of(), "darwin") == str(bundled / "deno")
    assert tool_path("deno", [], which_of("deno"), "linux") == "/bin/deno"
    assert tool_path("deno", [], which_of(), "linux") is None
    (bundled / "deno.exe").write_bytes(b"")
    assert tool_path("deno", [bundled], which_of(), "win32") == str(bundled / "deno.exe")


def test_no_window_only_on_windows():
    import subprocess
    assert no_window("darwin") == {} and no_window("linux") == {}
    assert no_window("win32") == {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}


def test_open_command_per_os():
    assert open_command("darwin", "/x y") == ["open", "/x y"]
    assert open_command("linux", "/x") == ["xdg-open", "/x"]
    assert open_command("win32", "C:/x") is None  # os.startfile is used instead


def test_reveal_command_and_label_per_os():
    from youtube_download.core.system import reveal_command, reveal_label

    assert reveal_command("darwin", "/m/a b.mp3") == ["open", "-R", "/m/a b.mp3"]
    assert reveal_command("win32", r"C:\m\a.mp3") == ["explorer", r"/select,C:\m\a.mp3"]
    assert reveal_command("linux", "/m/a.mp3") == ["xdg-open", str(Path("/m"))]  # no portable "select"
    assert reveal_label("darwin") == "Mostrar en Finder"
    assert reveal_label("win32") == "Mostrar en el Explorador"
    assert reveal_label("linux") == "Mostrar en la carpeta"
