"""Illustrated profile pictures for demo staff: a simple bust on a soft background,
drawn pixel by pixel into a PNG (no imaging library needed). Fictional people only."""

import struct
import zlib
from collections.abc import Callable

Color = tuple[int, int, int]
SIZE = 256

SKINS: list[Color] = [(241, 205, 178), (226, 180, 146), (200, 150, 115)]
HAIRS: list[Color] = [(45, 35, 30), (90, 60, 40), (25, 25, 30)]


def _png(rows: list[bytes]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _ellipse(cx: float, cy: float, rx: float, ry: float) -> Callable[[int, int], bool]:
    return lambda x, y: ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1


def portrait(seed: int, *, scarf: bool, background: Color, clothes: Color) -> bytes:
    """``scarf`` draws a headscarf (as in the design concepts); otherwise short hair and
    a light beard on every other seed."""
    skin = SKINS[seed % len(SKINS)]
    hair = HAIRS[seed % len(HAIRS)]
    face = _ellipse(128, 120, 44, 54)
    shoulders = _ellipse(128, 275, 104, 84)
    eyes = [_ellipse(111, 116, 4.5, 5), _ellipse(145, 116, 4.5, 5)]
    if scarf:
        cover = _ellipse(128, 118, 64, 76)
        drape = _ellipse(128, 205, 78, 52)
        scarf_color = ((clothes[0] + 120) // 2, (clothes[1] + 90) // 2, (clothes[2] + 110) // 2)
    else:
        top = _ellipse(128, 86, 50, 36)
        beard = seed % 2 == 0
    light = tuple(min(255, c + 22) for c in background)
    rows = []
    for y in range(SIZE):
        row = bytearray()
        for x in range(SIZE):
            t = y / SIZE
            color: tuple[int, ...] = tuple(
                int(light[i] * (1 - t) + background[i] * t) for i in range(3)
            )
            if shoulders(x, y):
                color = clothes
            if scarf:
                if cover(x, y) or drape(x, y):
                    color = scarf_color
            elif 108 <= x <= 148 and 150 <= y <= 205:  # neck
                color = tuple(int(c * 0.92) for c in skin)
            if face(x, y):
                color = skin
                if not scarf and beard and y > 140:
                    color = tuple((c + h * 2) // 3 for c, h in zip(skin, hair, strict=True))
                if any(eye(x, y) for eye in eyes):
                    color = (40, 32, 30)
            if not scarf and top(x, y) and y < 92:
                color = hair
            row += bytes(color)
        rows.append(bytes(row))
    return _png(rows)
