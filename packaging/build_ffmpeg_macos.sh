#!/usr/bin/env bash
# Build a minimal, statically linked LGPL ffmpeg + ffprobe for macOS (no --enable-gpl, no nonfree).
# There is no verifiable third-party LGPL static macOS build, so we compile pinned, checksummed sources.
# Usage: packaging/build_ffmpeg_macos.sh <output-dir>
set -euo pipefail

FFMPEG_VERSION=8.1.3
FFMPEG_SHA256=7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3
LAME_VERSION=3.100
LAME_SHA256=ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e

OUT="$(mkdir -p "$1" && cd "$1" && pwd)"
WORK="$(mktemp -d)"
PREFIX="$WORK/prefix"
JOBS="$(sysctl -n hw.ncpu)"
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-12.0}"
cd "$WORK"

fetch() {  # url file sha256
  curl -fsSL --retry 3 -o "$2" "$1"
  echo "$3  $2" | shasum -a 256 -c -
}

fetch "https://downloads.sourceforge.net/project/lame/lame/$LAME_VERSION/lame-$LAME_VERSION.tar.gz" lame.tar.gz "$LAME_SHA256"
fetch "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" ffmpeg.tar.xz "$FFMPEG_SHA256"

tar xzf lame.tar.gz
(cd "lame-$LAME_VERSION" && ./configure --prefix="$PREFIX" --disable-shared --enable-static --disable-frontend \
  --disable-dependency-tracking && make -j"$JOBS" && make install)

tar xJf ffmpeg.tar.xz
cd "ffmpeg-$FFMPEG_VERSION"
# --disable-autodetect keeps Homebrew/GPL libraries out; only macOS system frameworks and LGPL lame are linked.
./configure --prefix="$PREFIX" --disable-shared --enable-static --disable-autodetect \
  --disable-doc --disable-ffplay --disable-debug \
  --enable-libmp3lame --enable-securetransport --enable-audiotoolbox --enable-videotoolbox \
  --enable-zlib --enable-bzlib \
  --extra-cflags="-I$PREFIX/include" --extra-ldflags="-L$PREFIX/lib"
make -j"$JOBS"

cp ffmpeg ffprobe "$OUT/"
cp COPYING.LGPLv2.1 "$OUT/LICENSE-ffmpeg.txt"
cp "$WORK/lame-$LAME_VERSION/COPYING" "$OUT/LICENSE-lame.txt"
"$OUT/ffmpeg" -hide_banner -version | grep -q -- "--enable-gpl" && { echo "GPL build detected" >&2; exit 1; }
echo "ffmpeg $FFMPEG_VERSION (LGPL) -> $OUT"
rm -rf "$WORK"
