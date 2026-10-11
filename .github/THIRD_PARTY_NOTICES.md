# Third-party notices

This application is licensed under the **GNU General Public License v3.0 or later** (see [`LICENSE`](../LICENSE)).

The installers (Windows `.exe`, macOS `.dmg`, Linux `.AppImage`) bundle the components below. Each keeps its own license. Licenses were taken from the installed package metadata (`License-Expression` / `License` fields), the license headers of the shipped files, or the upstream project, for the versions pinned in `uv.lock` and `packaging/`. When a version changes, re-check its license.

A copy of this file and of `LICENSE` is shipped inside every installer, next to the app.

## Runtime and application frameworks

| Component | Version | License | Source |
|---|---|---|---|
| CPython | 3.14 | PSF-2.0 | https://www.python.org/downloads/source/ |
| NiceGUI | 3.18.0 | MIT | https://github.com/zauberzeug/nicegui |
| Quasar (bundled by NiceGUI) | 2.18.5 | MIT | https://github.com/quasarframework/quasar |
| Vue (bundled by NiceGUI) | 3.5.22 | MIT | https://github.com/vuejs/core |
| FastAPI | 0.143.0 | MIT | https://github.com/fastapi/fastapi |
| Starlette | 1.7.0 | BSD-3-Clause | https://github.com/Kludex/starlette |
| Uvicorn | 0.54.0 | BSD-3-Clause | https://github.com/Kludex/uvicorn |
| python-socketio / python-engineio | 5.17.0 / 4.14.0 | MIT | https://github.com/miguelgrinberg/python-socketio |
| Pydantic / pydantic-core | 2.14.0 / 2.50.0 | MIT | https://github.com/pydantic/pydantic |
| pywebview | 6.2.1 | BSD-3-Clause | https://github.com/r0x0r/pywebview |
| PyObjC (macOS only) | 12.2.2 | MIT | https://github.com/ronaldoussoren/pyobjc |
| pythonnet (Windows only) | 3.2.1 | MIT | https://github.com/pythonnet/pythonnet |
| Microsoft Edge WebView2 Evergreen Bootstrapper (Windows installer, run only if WebView2 is missing) | latest | Microsoft software license terms | https://developer.microsoft.com/microsoft-edge/webview2/ |

## Downloading and media

| Component | Version | License | Source |
|---|---|---|---|
| yt-dlp | 2026.8.19 | Unlicense | https://github.com/yt-dlp/yt-dlp |
| yt-dlp-ejs (YouTube JS challenge solver scripts) | 0.8.0 | Unlicense AND MIT AND ISC | https://github.com/yt-dlp/ejs |
| Deno (JavaScript runtime used by yt-dlp-ejs; binary from the `deno` wheel) | 2.9.7 | MIT (license text shipped as `deno/LICENSE-deno.txt`) | https://github.com/denoland/deno |
| Mutagen (audio tags; reads embedded covers) | 1.48.1 | GPL-2.0-or-later | https://github.com/quodlibet/mutagen |
| requests / urllib3 | 2.34.2 / 2.8.0 | Apache-2.0 / MIT | https://github.com/psf/requests, https://github.com/urllib3/urllib3 |
| certifi | 2026.7.22 | MPL-2.0 | https://github.com/certifi/python-certifi |
| Brotli | 1.2.0 | MIT | https://github.com/google/brotli |
| PyCryptodomex | 3.24.0 | BSD-2-Clause and Public Domain | https://github.com/Legrandin/pycryptodome |
| websockets | 17.2 | BSD-3-Clause | https://github.com/python-websockets/websockets |

Other pure-Python dependencies pulled in by the packages above (e.g. anyio, h11, httptools, idna, charset-normalizer, aiohttp, yarl, multidict, orjson, Jinja2, MarkupSafe, bidict, watchfiles, uvloop) are MIT, BSD, Apache-2.0, MPL-2.0 or PSF-2.0 licensed; their exact versions are pinned in `uv.lock` and their license is in each package's metadata (`pip show <package>` or the `*.dist-info` folder).

## FFmpeg and LAME (LGPL)

The bundled `ffmpeg` and `ffprobe` are **LGPL** builds: no `--enable-gpl`, no `--enable-nonfree`. The release workflow fails if `ffmpeg -version` shows `--enable-gpl`. They are separate executables called by yt-dlp, not linked into the app. Their license texts are shipped next to the binaries (`ffmpeg/LICENSE-ffmpeg.txt`, and `ffmpeg/LICENSE-lame.txt` on macOS).

| Platform | Build | License | Exact source |
|---|---|---|---|
| Windows x64 | BtbN FFmpeg-Builds `ffmpeg-n8.1.3-17-gc389840894-win64-lgpl-8.1.zip` (release `autobuild-2026-10-10-13-04`, SHA-256 pinned in `packaging/build.py`) | LGPL (v3 variant, `--enable-version3`), with LAME (LGPL) | https://github.com/BtbN/FFmpeg-Builds (build scripts) · FFmpeg source at commit `c389840894`: https://github.com/FFmpeg/FFmpeg/commit/c389840894 |
| Linux x86_64 | BtbN FFmpeg-Builds `ffmpeg-n8.1.3-17-gc389840894-linux64-lgpl-8.1.tar.xz` (same release, SHA-256 pinned) | LGPL (v3 variant), with LAME (LGPL) | as above |
| macOS arm64 | Compiled in CI by `packaging/build_ffmpeg_macos.sh` from FFmpeg 8.1.3 (`ffmpeg-8.1.3.tar.xz`, SHA-256 `7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3`) and LAME 3.100 (`lame-3.100.tar.gz`, SHA-256 `ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e`). The configure flags are in the script and are printed by `ffmpeg -version`. | LGPL-2.1-or-later (FFmpeg), LGPL-2.0-or-later (LAME) | https://ffmpeg.org/releases/ffmpeg-8.1.3.tar.xz · https://sourceforge.net/projects/lame/files/lame/3.100/ |

To get the corresponding source for any release, check out the matching tag of this repository: the URLs and checksums above are pinned there.

## Linux build only: Qt

The Linux AppImage uses pywebview's Qt backend.

| Component | Version | License | Source |
|---|---|---|---|
| PyQt6 | 6.11.0 | GPL-3.0-only | https://www.riverbankcomputing.com/software/pyqt/ |
| PyQt6-WebEngine | 6.11.0 | GPL-3.0-only | https://www.riverbankcomputing.com/software/pyqtwebengine/ |
| Qt 6 / Qt WebEngine binaries (`PyQt6-Qt6`, `PyQt6-WebEngine-Qt6`) | 6.11.2 | LGPL-3.0 (Qt WebEngine also contains Chromium, under BSD-3-Clause and other permissive licenses) | https://download.qt.io/official_releases/qt/ |
| QtPy | 2.4.3 | MIT | https://github.com/spyder-ide/qtpy |

Because PyQt6 is GPL-3.0-only, the Linux AppImage as a whole is distributed under GPL-3.0. This is compatible with this project's GPL-3.0-or-later license.

## Packaging tools

| Component | License | Notes |
|---|---|---|
| PyInstaller 6.22.3 (bootloader) | GPL-2.0-or-later with the PyInstaller bootloader exception | The exception allows distributing the bootloader with programs under any license. https://github.com/pyinstaller/pyinstaller |
| Inno Setup 6 (Windows installer) | Inno Setup License (permissive) | https://jrsoftware.org/isinfo.php |
| appimagetool 1.9.1 / AppImage type2-runtime 20251108 (Linux) | MIT (embedded third-party parts keep their own licenses) | https://github.com/AppImage/appimagetool |

## Fonts

The UI asks Google Fonts for IBM Plex Sans and IBM Plex Mono (SIL Open Font License 1.1) at runtime; they are not bundled.
