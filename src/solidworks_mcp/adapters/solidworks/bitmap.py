"""Turn ``IModelDoc2.SaveBMP`` output into PNG/JPEG and read image sizes.

``SaveBMP(path, width, height)`` is the only SolidWorks call that renders the
view at a caller-chosen pixel size; ``SaveAs3`` to ``.png`` always writes the
window's size. It only writes BMP, so a PNG is produced here with the
standard library (``zlib``) - Pillow is an optional extra and absent from the
server's environment. JPEG needs Pillow and reports ``ImportError`` without
it, so the caller can fall back.

``SaveBMP`` keeps the window's framing, so an image whose aspect differs
from the window's crops the zoomed-to-fit model. The caller therefore
renders at the window's aspect and :func:`pad` extends the picture to the
requested size by repeating its edge pixels (the background).
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def read_bmp(path: str | Path) -> tuple[int, int, list[bytes]]:
    """Read an uncompressed 24/32-bit BMP.

    Returns:
        tuple[int, int, list[bytes]]: Width, height and the RGB rows, top
        row first.

    Raises:
        ValueError: When the file is not an uncompressed 24/32-bit BMP.
    """
    data = Path(path).read_bytes()
    if len(data) < 54 or data[:2] != b"BM":
        raise ValueError(f"{path} is not a BMP file")
    offset = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    bits, compression = struct.unpack_from("<HI", data, 28)
    # BI_RGB (0), or BI_BITFIELDS (3) with the standard BGRA masks at 32 bpp.
    if bits not in (24, 32) or compression not in (0, 3) or width <= 0:
        raise ValueError(
            f"{path}: unsupported BMP ({bits} bpp, compression {compression})"
        )
    step = bits // 8
    stride = (width * step + 3) & ~3
    top_down = height < 0
    height = abs(height)
    rows = []
    for index in range(height):
        start = offset + index * stride
        bgr = data[start : start + width * step]
        rgb = bytearray(width * 3)
        rgb[0::3] = bgr[2::step]
        rgb[1::3] = bgr[1::step]
        rgb[2::3] = bgr[0::step]
        rows.append(bytes(rgb))
    if not top_down:
        rows.reverse()
    return width, height, rows


def fit_aspect(width: int, height: int, aspect: float) -> tuple[int, int]:
    """Largest ``aspect`` (width / height) size that fits in ``width`` x ``height``."""
    if width / height > aspect:
        return max(1, round(height * aspect)), height
    return width, max(1, round(width / aspect))


def pad(
    width: int, height: int, rows: list[bytes], target: tuple[int, int]
) -> list[bytes]:
    """Centre RGB ``rows`` in a ``target`` canvas, repeating the edge pixels.

    Raises:
        ValueError: When the image is larger than ``target``.
    """
    target_w, target_h = target
    if width > target_w or height > target_h:
        raise ValueError(f"{width}x{height} does not fit in {target_w}x{target_h}")
    left = (target_w - width) // 2
    right = target_w - width - left
    widened = [row[:3] * left + row + row[-3:] * right for row in rows]
    top = (target_h - height) // 2
    bottom = target_h - height - top
    return [widened[0]] * top + widened + [widened[-1]] * bottom


def write_bmp(path: str | Path, width: int, height: int, rows: list[bytes]) -> None:
    """Write RGB rows (top first) as a bottom-up 24-bit BMP."""
    stride = (width * 3 + 3) & ~3
    body = bytearray()
    for row in reversed(rows):
        bgr = bytearray(width * 3)
        bgr[0::3] = row[2::3]
        bgr[1::3] = row[1::3]
        bgr[2::3] = row[0::3]
        body += bgr + b"\x00" * (stride - width * 3)
    header = struct.pack(
        "<2sIHHIIiiHHIIiiII",
        *(b"BM", 54 + len(body), 0, 0, 54, 40, width, height, 1, 24, 0),
        *(len(body), 2835, 2835, 0, 0),
    )
    Path(path).write_bytes(header + bytes(body))


def write_png(path: str | Path, width: int, height: int, rows: list[bytes]) -> None:
    """Write 8-bit RGB rows (top first) as a PNG."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + row for row in rows)
    Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def convert_bmp(
    source: str | Path, target: str | Path, size: tuple[int, int] | None = None
) -> None:
    """Convert a BMP to the format named by ``target``'s extension.

    Args:
        source: The BMP ``SaveBMP`` wrote.
        target: Output path; ``.png``, ``.bmp``, ``.jpg`` or ``.jpeg``.
        size: Pad the picture to this ``(width, height)`` (see :func:`pad`).

    Raises:
        ImportError: For JPEG when Pillow is not installed.
        ValueError: For any other extension, a BMP that :func:`read_bmp`
            cannot read, or one larger than ``size``.
    """
    suffix = Path(target).suffix.lower()
    if suffix not in (".png", ".bmp", ".jpg", ".jpeg"):
        raise ValueError(f"Cannot convert a BMP to {suffix!r}")
    width, height, rows = read_bmp(source)
    if size is not None:
        rows = pad(width, height, rows, size)
        width, height = size
    if suffix == ".png":
        write_png(target, width, height, rows)
    elif suffix == ".bmp":
        write_bmp(target, width, height, rows)
    else:
        from PIL import Image

        image = Image.frombytes("RGB", (width, height), b"".join(rows))
        image.save(target, "JPEG", quality=92)


def image_size(path: str | Path) -> tuple[int, int] | None:
    """Return ``(width, height)`` of a PNG, BMP or JPEG, or ``None``."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack_from(">II", data, 16)
    if data[:2] == b"BM" and len(data) >= 26:
        width, height = struct.unpack_from("<ii", data, 18)
        return width, abs(height)
    if data[:2] == b"\xff\xd8":
        index = 2
        while index + 9 <= len(data) and data[index] == 0xFF:
            marker = data[index + 1]
            length = struct.unpack_from(">H", data, index + 2)[0]
            # SOF0..SOF15 carry the frame size; C4/C8/CC are not frames.
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height, width = struct.unpack_from(">HH", data, index + 5)
                return width, height
            index += 2 + length
    return None
