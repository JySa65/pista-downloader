"""Build the installer for the current OS.

    uv sync --group build
    uv run python packaging/build.py [--ffmpeg-dir DIR] [--check-tag vX.Y.Z]

Output in dist/:
  macOS   YouTubeDownload-<v>-macos-arm64.dmg (unsigned .app inside)
  Windows YouTubeDownload-Setup-<v>.exe        (Inno Setup; needs ISCC.exe)
  Linux   YouTubeDownload-<v>-x86_64.AppImage  (Qt backend bundled)

ffmpeg/ffprobe are LGPL builds: BtbN `*-lgpl` archives on Windows/Linux (pinned + SHA256 below),
compiled from pinned sources on macOS (build_ffmpeg_macos.sh).
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
NAME = "YouTubeDownload"

BTBN = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-10-13-04/"
# ponytail: BtbN prunes old autobuilds; when a URL 404s, bump to a newer autobuild and its SHA256.
FFMPEG = {
    "windows": (BTBN + "ffmpeg-n8.1.3-17-gc389840894-win64-lgpl-8.1.zip",
                "82f65c2760d4b2f5c1cfb19268b1ea31ea919f8afbd107fd7bbad191b4d84c9c"),
    "linux": (BTBN + "ffmpeg-n8.1.3-17-gc389840894-linux64-lgpl-8.1.tar.xz",
              "a79d3e6d6767fc139406a3b82db499bb337b5293e8977996676072b1086e148c"),
}
APPIMAGETOOL = ("https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage",
                "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0")
APPIMAGE_RUNTIME = ("https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64",
                    "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d")


def target() -> str:
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]


def run(*cmd: str | Path) -> None:
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def fetch(url: str, sha256: str, dest: Path) -> Path:
    if not dest.exists():
        print("download", url, flush=True)
        urllib.request.urlretrieve(url, dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    if digest != sha256:
        dest.unlink()
        sys.exit(f"SHA256 mismatch for {url}: {digest}")
    return dest


def prepare_ffmpeg(out: Path) -> Path:
    """ffmpeg, ffprobe and license texts in `out` (reused if already there)."""
    exe = ".exe" if target() == "windows" else ""
    if (out / f"ffmpeg{exe}").is_file():
        return out
    out.mkdir(parents=True, exist_ok=True)
    if target() == "macos":
        run("bash", PKG / "build_ffmpeg_macos.sh", out)
        return out
    url, sha = FFMPEG[target()]
    archive = fetch(url, sha, BUILD / url.rsplit("/", 1)[1])
    opener = zipfile.ZipFile(archive) if archive.suffix == ".zip" else tarfile.open(archive)
    with opener as a:
        names = a.namelist() if isinstance(a, zipfile.ZipFile) else a.getnames()
        for name in names:
            base = name.rsplit("/", 1)[-1]
            if base in (f"ffmpeg{exe}", f"ffprobe{exe}", "LICENSE.txt"):
                data = a.read(name) if isinstance(a, zipfile.ZipFile) else a.extractfile(name).read()
                dest = out / ("LICENSE-ffmpeg.txt" if base == "LICENSE.txt" else base)
                dest.write_bytes(data)
                dest.chmod(0o755)
    return out


def pyinstaller(ffmpeg_dir: Path) -> None:
    import nicegui

    exe = ".exe" if target() == "windows" else ""
    sep = os.pathsep  # PyInstaller SRC<sep>DEST; ';' avoids clashing with Windows drive colons
    args = ["--noconfirm", "--clean", "--name", NAME, "--windowed", "--onedir",
            "--icon", PKG / "icon.png", "--osx-bundle-identifier", "io.github.jysa65.youtubedownload",
            "--add-data", f"{Path(nicegui.__file__).parent}{sep}nicegui",
            "--add-data", f"{ROOT / 'pyproject.toml'}{sep}.",
            "--add-binary", f"{ffmpeg_dir / ('ffmpeg' + exe)}{sep}ffmpeg",
            "--add-binary", f"{ffmpeg_dir / ('ffprobe' + exe)}{sep}ffmpeg"]
    for lic in ffmpeg_dir.glob("LICENSE*"):
        args += ["--add-data", f"{lic}{sep}ffmpeg"]
    if target() == "linux":
        args += ["--collect-submodules", "qtpy"]
    run(sys.executable, "-m", "PyInstaller", *args, "--distpath", DIST, "--workpath", BUILD / "pyinstaller",
        "--specpath", BUILD, ROOT / "main.py")


def package_macos(v: str) -> Path:
    stage = BUILD / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    shutil.copytree(DIST / f"{NAME}.app", stage / f"{NAME}.app", symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    dmg = DIST / f"{NAME}-{v}-macos-arm64.dmg"
    dmg.unlink(missing_ok=True)
    run("hdiutil", "create", "-volname", NAME, "-srcfolder", stage, "-ov", "-format", "UDZO", dmg)
    return dmg


def package_windows(v: str) -> Path:
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    run(iscc, f"/DAppVersion={v}", f"/DSourceDir={DIST / NAME}", f"/DOutputDir={DIST}", PKG / "installer.iss")
    return DIST / f"{NAME}-Setup-{v}.exe"


def package_linux(v: str) -> Path:
    appdir = BUILD / "AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(DIST / NAME, appdir / "usr" / "lib" / NAME, symlinks=True)
    shutil.copy(PKG / "icon.png", appdir / f"{NAME}.png")
    (appdir / f"{NAME}.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName=YouTube Download\nExec={NAME}\nIcon={NAME}\n"
        "Categories=AudioVideo;Network;\n")
    apprun = appdir / "AppRun"
    apprun.write_text(f'#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/lib/{NAME}/{NAME}" "$@"\n')
    apprun.chmod(0o755)
    tool = fetch(*APPIMAGETOOL, BUILD / "appimagetool.AppImage")
    tool.chmod(0o755)
    runtime = fetch(*APPIMAGE_RUNTIME, BUILD / "runtime-x86_64")
    out = DIST / f"{NAME}-{v}-x86_64.AppImage"
    os.environ["APPIMAGE_EXTRACT_AND_RUN"] = "1"  # CI runners have no FUSE
    os.environ["ARCH"] = "x86_64"
    run(tool, "--runtime-file", runtime, appdir, out)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ffmpeg-dir", type=Path, default=BUILD / "ffmpeg")
    p.add_argument("--check-tag", help="fail unless this tag (vX.Y.Z) matches pyproject version")
    p.add_argument("--skip-package", action="store_true", help="stop after PyInstaller")
    a = p.parse_args()
    v = version()
    if a.check_tag is not None:
        if a.check_tag != f"v{v}":
            sys.exit(f"Tag {a.check_tag} does not match pyproject version {v}")
        print(f"tag {a.check_tag} matches version {v}")
        return
    BUILD.mkdir(exist_ok=True)
    pyinstaller(prepare_ffmpeg(a.ffmpeg_dir))
    if not a.skip_package:
        out = {"macos": package_macos, "windows": package_windows, "linux": package_linux}[target()](v)
        print("built", out)


if __name__ == "__main__":
    main()
