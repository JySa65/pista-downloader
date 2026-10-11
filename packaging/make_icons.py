"""Regenerate the app icons from packaging/icon.svg (the single source).

    uv run --no-project --with resvg-py --with pillow python packaging/make_icons.py

resvg-py ships self-contained wheels (no system SVG/cairo library needed).
Writes icon.png (1024), icon.ico (16-256) and, on macOS, icon.icns (via iconutil).
The design thickens the tile outline at small sizes (stroke 2 at 32 px, 3 at <= 20 px).
"""
import io
import subprocess
import sys
import tempfile
from pathlib import Path

import resvg_py
from PIL import Image

PKG = Path(__file__).resolve().parent
SVG = (PKG / "icon.svg").read_text("utf-8")


def stroke_for(size: int) -> str:
    return "3" if size <= 20 else "2" if size <= 32 else "1"


def render(size: int) -> Image.Image:
    svg = SVG.replace('stroke-width="1"', f'stroke-width="{stroke_for(size)}"', 1)
    png = bytes(resvg_py.svg_to_bytes(svg_string=svg, width=size, height=size))
    return Image.open(io.BytesIO(png)).convert("RGBA")


def main() -> None:
    render(1024).save(PKG / "icon.png")
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [render(s) for s in ico_sizes]
    frames[-1].save(PKG / "icon.ico", sizes=[(s, s) for s in ico_sizes], append_images=frames[:-1])
    if sys.platform == "darwin":
        with tempfile.TemporaryDirectory() as tmp:
            iconset = Path(tmp) / "icon.iconset"
            iconset.mkdir()
            for s in (16, 32, 128, 256, 512):
                render(s).save(iconset / f"icon_{s}x{s}.png")
                render(s * 2).save(iconset / f"icon_{s}x{s}@2x.png")
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(PKG / "icon.icns")], check=True)
    else:
        print("icon.icns not regenerated (needs macOS iconutil)")
    print("icons written to", PKG)


if __name__ == "__main__":
    main()
