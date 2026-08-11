#!/usr/bin/env python3
"""
Generate placeholder PNG icons for the PWA using only the Python standard
library (zlib + struct) -- no Pillow/image libraries required.

Produces a flat navy square with a red horizontal band and a white "R",
at the three sizes iOS/PWA manifests need. Run once; regenerate any time
by re-running this script.

Usage: python3 scripts/make_icons.py
"""
import struct
import zlib
from pathlib import Path

ICONS_DIR = Path(__file__).resolve().parent.parent / "icons"

NAVY = (13, 18, 32)
RED = (200, 30, 30)
WHITE = (240, 242, 250)

# A crude 5x7 bitmap font, just enough to draw "R".
LETTER_R = [
    "1111 ",
    "1   1",
    "1111 ",
    "11   ",
    "1 1  ",
    "1  1 ",
    "1   1",
]


def make_png(size, path):
    pixels = [[NAVY for _ in range(size)] for _ in range(size)]

    band_top = int(size * 0.62)
    band_bottom = int(size * 0.78)
    for y in range(band_top, band_bottom):
        for x in range(size):
            pixels[y][x] = RED

    # Draw a big "R" centered in the upper portion, scaled to the icon size.
    scale = max(1, size // 40)
    glyph_w = len(LETTER_R[0]) * scale
    glyph_h = len(LETTER_R) * scale
    off_x = (size - glyph_w) // 2
    off_y = int(size * 0.18)
    for row_i, row in enumerate(LETTER_R):
        for col_i, ch in enumerate(row):
            if ch != "1":
                continue
            for dy in range(scale):
                for dx in range(scale):
                    y = off_y + row_i * scale + dy
                    x = off_x + col_i * scale + dx
                    if 0 <= y < size and 0 <= x < size:
                        pixels[y][x] = WHITE

    write_png(pixels, size, path)


def write_png(pixels, size, path):
    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for row in pixels:
        raw.append(0)  # no filter
        for (r, g, b) in row:
            raw += bytes((r, g, b))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(bytes(raw), 9)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", idat)
    png += chunk(b"IEND", b"")

    path.write_bytes(png)
    print(f"wrote {path} ({size}x{size})")


def main():
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    make_png(192, ICONS_DIR / "icon-192.png")
    make_png(512, ICONS_DIR / "icon-512.png")
    make_png(180, ICONS_DIR / "apple-touch-icon.png")


if __name__ == "__main__":
    main()
