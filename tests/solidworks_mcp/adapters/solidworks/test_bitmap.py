"""Tests for solidworks_mcp.adapters.solidworks.bitmap (SaveBMP -> PNG/JPEG)."""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from solidworks_mcp.adapters.solidworks import bitmap

# Two rows of two pixels, top row first: red, green / blue, white.
_TOP = [(255, 0, 0), (0, 255, 0)]
_BOTTOM = [(0, 0, 255), (255, 255, 255)]


def _bmp(path: Path, bits: int = 24, top_down: bool = False, compression=0) -> Path:
    step = bits // 8
    stride = (2 * step + 3) & ~3
    rows = [_TOP, _BOTTOM] if top_down else [_BOTTOM, _TOP]
    pixels = b""
    for row in rows:
        raw = b"".join(bytes([b, g, r] + [0] * (step - 3)) for r, g, b in row)
        pixels += raw + b"\x00" * (stride - len(raw))
    header = struct.pack(
        "<2sIHHIIiiHHIIiiII",
        *(b"BM", 54 + len(pixels), 0, 0, 54, 40, 2, -2 if top_down else 2),
        *(1, bits, compression, len(pixels), 2835, 2835, 0, 0),
    )
    path.write_bytes(header + pixels)
    return path


def _rgb(rows: list[list[tuple[int, int, int]]]) -> list[bytes]:
    return [b"".join(bytes(p) for p in row) for row in rows]


@pytest.mark.parametrize(
    ("bits", "top_down"), [(24, False), (32, True), (32, False), (24, True)]
)
def test_read_bmp_returns_rgb_rows_top_first(tmp_path, bits, top_down) -> None:
    path = _bmp(tmp_path / "in.bmp", bits=bits, top_down=top_down)

    assert bitmap.read_bmp(path) == (2, 2, _rgb([_TOP, _BOTTOM]))


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"GIF89a" + b"\x00" * 60, "is not a BMP file"),
        (b"BM", "is not a BMP file"),
    ],
)
def test_read_bmp_rejects_other_files(tmp_path, content, message) -> None:
    path = tmp_path / "x.bmp"
    path.write_bytes(content)
    with pytest.raises(ValueError, match=message):
        bitmap.read_bmp(path)


def test_read_bmp_rejects_compressed_bitmaps(tmp_path) -> None:
    path = _bmp(tmp_path / "rle.bmp", compression=1)
    with pytest.raises(ValueError, match="unsupported BMP"):
        bitmap.read_bmp(path)


def test_write_png_round_trips_through_zlib(tmp_path) -> None:
    out = tmp_path / "out.png"
    bitmap.write_png(out, 2, 2, _rgb([_TOP, _BOTTOM]))

    data = out.read_bytes()
    assert bitmap.image_size(out) == (2, 2)
    idat = data.index(b"IDAT")
    length = struct.unpack(">I", data[idat - 4 : idat])[0]
    raw = zlib.decompress(data[idat + 4 : idat + 4 + length])
    assert raw == b"\x00" + _rgb([_TOP])[0] + b"\x00" + _rgb([_BOTTOM])[0]


def test_convert_bmp_to_png(tmp_path) -> None:
    out = tmp_path / "out.PNG"
    bitmap.convert_bmp(_bmp(tmp_path / "in.bmp"), out)
    assert bitmap.image_size(out) == (2, 2)


def test_convert_bmp_to_jpeg_needs_pillow(tmp_path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "PIL", None)
    with pytest.raises(ImportError):
        bitmap.convert_bmp(_bmp(tmp_path / "in.bmp"), tmp_path / "out.jpg")


def test_convert_bmp_to_jpeg_with_pillow(tmp_path, monkeypatch) -> None:
    calls: list[tuple] = []

    def _frombytes(mode, size, data):
        calls.append(("frombytes", mode, size, data))
        return SimpleNamespace(save=lambda *a, **k: calls.append(("save", a, k)))

    pil = ModuleType("PIL")
    pil.Image = SimpleNamespace(frombytes=_frombytes)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "PIL", pil)

    target = tmp_path / "out.jpeg"
    bitmap.convert_bmp(_bmp(tmp_path / "in.bmp"), target)

    assert calls == [
        ("frombytes", "RGB", (2, 2), b"".join(_rgb([_TOP, _BOTTOM]))),
        ("save", (target, "JPEG"), {"quality": 92}),
    ]


def test_convert_bmp_pads_to_the_requested_size(tmp_path) -> None:
    out = tmp_path / "out.bmp"
    bitmap.convert_bmp(_bmp(tmp_path / "in.bmp"), out, size=(4, 3))

    width, height, rows = bitmap.read_bmp(out)
    red, green, blue, white = (bytes(p) for p in _TOP + _BOTTOM)
    assert (width, height) == (4, 3)
    assert rows == [
        red + red + green + green,
        blue + blue + white + white,
        blue + blue + white + white,  # the odd spare row goes at the bottom
    ]


def test_pad_refuses_a_larger_image() -> None:
    with pytest.raises(ValueError, match="2x2 does not fit in 1x4"):
        bitmap.pad(2, 2, _rgb([_TOP, _BOTTOM]), (1, 4))


@pytest.mark.parametrize(
    ("size", "aspect", "expected"),
    [
        ((640, 480), 2273 / 1324, (640, 373)),  # narrower than the window
        ((800, 200), 2273 / 1324, (343, 200)),  # wider than the window
        ((300, 300), 1.0, (300, 300)),
    ],
)
def test_fit_aspect(size, aspect, expected) -> None:
    assert bitmap.fit_aspect(*size, aspect) == expected


def test_convert_bmp_rejects_other_formats(tmp_path) -> None:
    with pytest.raises(ValueError, match="Cannot convert a BMP to '.tif'"):
        bitmap.convert_bmp(_bmp(tmp_path / "in.bmp"), tmp_path / "out.tif")


def _jpeg(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    dht = b"\xff\xc4" + struct.pack(">H", 5) + b"\x00\x00\x00"
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x00" * 3
    return b"\xff\xd8" + app0 + dht + sof + b"\xff\xd9"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (_jpeg(1280, 720), (1280, 720)),
        (b"\xff\xd8\xff\xd9", None),  # JPEG with no frame header
        (b"plain text", None),
    ],
)
def test_image_size_reads_headers(tmp_path, content, expected) -> None:
    path = tmp_path / "img"
    path.write_bytes(content)
    assert bitmap.image_size(path) == expected


def test_image_size_of_bmp_and_missing_file(tmp_path) -> None:
    assert bitmap.image_size(_bmp(tmp_path / "in.bmp", top_down=True)) == (2, 2)
    assert bitmap.image_size(tmp_path / "missing.png") is None
