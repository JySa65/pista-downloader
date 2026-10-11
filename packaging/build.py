"""Build the installer for the current OS.

    uv sync --group build
    uv run python packaging/build.py [--ffmpeg-dir DIR] [--check-tag vX.Y.Z]

Output in dist/:
  macOS   Pista-<v>-macos-arm64.dmg (unsigned .app inside)
  Windows Pista-Setup-<v>.exe        (Inno Setup; needs ISCC.exe)
  Linux   Pista-<v>-x86_64.AppImage  (Qt backend bundled)

ffmpeg/ffprobe are LGPL builds: BtbN `*-lgpl` archives on Windows/Linux (pinned + SHA256 below),
compiled from pinned sources on macOS (build_ffmpeg_macos.sh).

PO Tokens: the bgutil yt-dlp plugin ships as real files in yt-dlp-plugins/ and its generator (fetched by
fetch_pot_server.py, needs network) in bgutil-server/. A failed fetch fails the build.
"""
import argparse
import datetime
import json
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
NOTICES = ROOT / ".github" / "THIRD_PARTY_NOTICES.md"
PKG = ROOT / "packaging"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
NAME = "Pista"

BTBN = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-10-10-13-04/"
# ponytail: BtbN prunes old autobuilds; when a URL 404s, bump to a newer autobuild and its SHA256.
FFMPEG = {
    "windows": (BTBN + "ffmpeg-n8.1.3-17-gc389840894-win64-lgpl-8.1.zip",
                "82f65c2760d4b2f5c1cfb19268b1ea31ea919f8afbd107fd7bbad191b4d84c9c"),
    "linux": (BTBN + "ffmpeg-n8.1.3-17-gc389840894-linux64-lgpl-8.1.tar.xz",
              "a79d3e6d6767fc139406a3b82db499bb337b5293e8977996676072b1086e148c"),
}
# Evergreen bootstrapper: always the latest file, so it is checked by Microsoft's Authenticode signature, not a hash.
WEBVIEW2_BOOTSTRAPPER = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
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


def pyinstaller(ffmpeg_dir: Path, pot_server: Path) -> None:
    import nicegui

    exe = ".exe" if target() == "windows" else ""
    icon = PKG / {"macos": "icon.icns", "windows": "icon.ico"}.get(target(), "icon.png")
    sep = os.pathsep  # PyInstaller SRC<sep>DEST; ';' avoids clashing with Windows drive colons
    args = ["--noconfirm", "--clean", "--name", NAME, "--windowed", "--onedir",
            "--icon", icon, "--osx-bundle-identifier", "io.github.jysa65.pista",
            "--add-data", f"{Path(nicegui.__file__).parent}{sep}nicegui",
            "--add-data", f"{ROOT / 'pyproject.toml'}{sep}.",
            "--add-data", f"{PKG / 'icon.png'}{sep}.",  # Linux window icon
            "--add-data", f"{ROOT / 'LICENSE'}{sep}.",
            "--add-data", f"{NOTICES}{sep}.",
            "--add-data", f"{build_info()}{sep}.",
            "--add-binary", f"{ffmpeg_dir / ('ffmpeg' + exe)}{sep}ffmpeg",
            "--add-binary", f"{ffmpeg_dir / ('ffprobe' + exe)}{sep}ffmpeg"]
    for lic in ffmpeg_dir.glob("LICENSE*"):
        args += ["--add-data", f"{lic}{sep}ffmpeg"]
    args += deno_args(sep) + pot_plugin_args(sep)
    if target() == "linux":
        args += ["--collect-submodules", "qtpy"]
    run(sys.executable, "-m", "PyInstaller", *args, "--distpath", DIST, "--workpath", BUILD / "pyinstaller",
        "--specpath", BUILD, ROOT / "main.py")
    add_pot_server(pot_server)


def build_info() -> Path:
    """build_info.json with the build date shown in «Acerca de» (UTC, YYYY.MM.DD)."""
    path = BUILD / "build_info.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": datetime.datetime.now(datetime.UTC).strftime("%Y.%m.%d")}), "utf-8")
    return path


def deno_args(sep: str) -> list[str]:
    """Bundle Deno (MIT, from the `deno` wheel pinned with hashes in uv.lock) and yt-dlp's EJS solver scripts.

    YouTube now requires solving JS challenges; without a JS runtime yt-dlp falls back to limited
    clients and downloads may fail with HTTP 403.
    """
    import deno

    binary = Path(deno.find_deno_bin())
    lic = BUILD / "LICENSE-deno.txt"
    dist_info = next(Path(deno.__file__).parent.parent.glob("deno-*.dist-info"))
    shutil.copy(dist_info / "licenses" / "LICENSE", lic)
    return ["--add-binary", f"{binary}{sep}deno", "--add-data", f"{lic}{sep}deno",
            "--hidden-import", "yt_dlp_ejs", "--collect-all", "yt_dlp_ejs"]


def pot_plugin_args(sep: str) -> list[str]:
    """The bgutil PO Token plugin as real .py files: yt-dlp can't load plugins compiled into the archive.

    Layout `yt-dlp-plugins/<package>/yt_dlp_plugins/...`, the folder Pista hands to yt-dlp (plugin_dirs).
    """
    import importlib.metadata

    dist = importlib.metadata.distribution("bgutil-ytdlp-pot-provider")
    out = BUILD / "yt-dlp-plugins"
    shutil.rmtree(out, ignore_errors=True)
    for f in dist.files or []:
        if f.parts[0] == "yt_dlp_plugins" and f.suffix == ".py":
            dest = out / "bgutil-ytdlp-pot-provider" / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f.locate(), dest)
    if not any(out.rglob("getpot_bgutil_script.py")):
        sys.exit("bgutil-ytdlp-pot-provider plugin files not found: run `uv sync` first")
    # The plugin imports yt-dlp's PO Token API, which nothing else may import statically.
    return ["--add-data", f"{out}{sep}yt-dlp-plugins", "--collect-submodules", "yt_dlp.extractor.youtube.pot"]


def add_pot_server(server: Path) -> None:
    """Copy bgutil's generator next to the PyInstaller output, after it ran.

    Not via --add-data: PyInstaller drops node_modules' package symlinks and hoists canvas' native libraries.
    Links are kept (macOS .app/.dmg and AppImage preserve them); Windows gets real copies (Inno Setup
    installs no links). VERSION is copied last, so a partial copy is never used.
    """
    if target() == "macos":
        app = DIST / f"{NAME}.app"
        dest = app / "Contents" / "Resources" / "bgutil-server"
    else:
        dest = DIST / NAME / "_internal" / "bgutil-server"  # PyInstaller's onedir contents dir (_MEIPASS)
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    for name in ("src", "node_modules", "package.json", "deno.json", "VERSION"):
        if (server / name).is_dir():
            shutil.copytree(server / name, dest / name, symlinks=target() != "windows")
        else:
            shutil.copy2(server / name, dest / name)
    if target() == "macos":
        # _MEIPASS is Contents/Frameworks; link it like PyInstaller links its own data, then reseal the
        # bundle's ad-hoc signature over the new resources.
        (app / "Contents" / "Frameworks" / "bgutil-server").symlink_to("../Resources/bgutil-server")
        run("codesign", "--force", "--sign", "-", app)


def package_macos(v: str) -> Path:
    stage = BUILD / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    shutil.copytree(DIST / f"{NAME}.app", stage / f"{NAME}.app", symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    shutil.copy(ROOT / "LICENSE", stage / "LICENSE.txt")  # visible in the mounted .dmg too
    shutil.copy(NOTICES, stage / "THIRD_PARTY_NOTICES.md")
    dmg = DIST / f"{NAME}-{v}-macos-arm64.dmg"
    dmg.unlink(missing_ok=True)
    run("hdiutil", "create", "-volname", NAME, "-srcfolder", stage, "-ov", "-format", "UDZO", dmg)
    return dmg


def webview2_bootstrapper() -> Path:
    dest = BUILD / "MicrosoftEdgeWebview2Setup.exe"
    if not dest.exists():
        print("download", WEBVIEW2_BOOTSTRAPPER, flush=True)
        urllib.request.urlretrieve(WEBVIEW2_BOOTSTRAPPER, dest)
    check = ("Import-Module Microsoft.PowerShell.Security; "
             "$s = Get-AuthenticodeSignature -LiteralPath $env:WV2; "
             "if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') "
             "{ Write-Error \"bad signature: $($s.Status) $($s.SignerCertificate.Subject)\"; exit 1 }")
    # Windows PowerShell 5.1 must not inherit PSModulePath from a pwsh 7 parent (e.g. GitHub runners),
    # or it fails to autoload its own Security module.
    env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    subprocess.run(["powershell", "-NoProfile", "-Command", check], check=True, env={**env, "WV2": str(dest)})
    return dest


def package_windows(v: str) -> Path:
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    run(iscc, f"/DWebView2Setup={webview2_bootstrapper()}", f"/DAppVersion={v}", f"/DIconFile={PKG / 'icon.ico'}", f"/DSourceDir={DIST / NAME}", f"/DLicenseFile={ROOT / 'LICENSE'}", f"/DNoticesFile={NOTICES}", f"/DOutputDir={DIST}", PKG / "installer.iss")
    return DIST / f"{NAME}-Setup-{v}.exe"


def package_linux(v: str) -> Path:
    appdir = BUILD / "AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(DIST / NAME, appdir / "usr" / "lib" / NAME, symlinks=True)
    shutil.copy(PKG / "icon.png", appdir / f"{NAME}.png")
    shutil.copy(PKG / "icon.png", appdir / ".DirIcon")
    (appdir / f"{NAME}.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName=Pista\nComment=Descarga audio y video\nExec={NAME}\nIcon={NAME}\n"
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
    import fetch_pot_server  # next to this script

    pot_server = fetch_pot_server.main()  # first: a release without PO tokens must not ship silently
    pyinstaller(prepare_ffmpeg(a.ffmpeg_dir), pot_server)
    if not a.skip_package:
        out = {"macos": package_macos, "windows": package_windows, "linux": package_linux}[target()](v)
        print("built", out)


if __name__ == "__main__":
    main()
