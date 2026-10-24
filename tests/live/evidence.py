"""Print a live test's proof, and hold SolidWorks on it during a demo.

``evidence(label, payload)`` prints ``[evidence] <label>: <payload>`` (what
``tests/scripts/live_demo.ps1`` shows). When ``SW_DEMO_HOLD_SECONDS`` is set
it then pauses, so a person watching SolidWorks sees the state the line
proves before the test moves on or closes its documents. Normal live runs
leave it unset and are not slowed.

When ``SW_DEMO_CAPTURE_DIR`` is set, each line also saves a PNG of the
SolidWorks window with the label and payload captioned beneath it, named
``<test>-<NN>.png``. ``tests/scripts/make_demo_gif.py`` turns one test's
frames into a GIF for a pull request or the docs. The capture copies the
window's pixels (``PrintWindow``); it makes no SolidWorks API call.
"""

from __future__ import annotations

import os
import pprint
import re
import textwrap
import time
from pathlib import Path
from typing import Any

_FRAMES: dict[str, int] = {}
_CAPTION_WIDTH_CHARS = 110
_CAPTION_MAX_LINES = 14


def evidence(label: str, payload: Any) -> None:
    """Print one proof line, hold if asked, then capture it if asked.

    The capture comes after the hold so SolidWorks has finished redrawing the
    state the line proves.
    """
    print(f"\n[evidence] {label}: {payload}", flush=True)
    try:
        hold = float(os.getenv("SW_DEMO_HOLD_SECONDS", "0"))
    except ValueError:
        hold = 0.0
    if hold > 0:
        time.sleep(hold)
    capture_dir = os.getenv("SW_DEMO_CAPTURE_DIR")
    if capture_dir:
        try:
            _capture(Path(capture_dir), label, payload)
        except Exception as exc:  # noqa: BLE001 - a picture never fails a test
            print(f"[evidence] (capture skipped: {exc})", flush=True)


def _test_name() -> str:
    """The running test's function name, from ``PYTEST_CURRENT_TEST``."""
    current = os.getenv("PYTEST_CURRENT_TEST", "demo").split(" ")[0]
    return re.sub(r"[^\w-]+", "_", current.split("::")[-1]).strip("_") or "demo"


def _area(hwnd: int) -> int:
    """A window's on-screen area in pixels."""
    import win32gui

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return (right - left) * (bottom - top)


def _solidworks_window_image() -> Any:
    """Copy the SolidWorks main window's pixels, even if it is covered.

    The window is the largest one owned by ``sldworks.exe``. A title match
    also caught an editor with this repo open ("SolidworksMCP-python - Visual
    Studio Code") and captured it whenever it was in front.
    """
    import win32api
    import win32gui
    import win32process
    import win32ui
    from PIL import Image

    found: list[int] = []

    def _match(hwnd: int, _: Any) -> None:
        if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
            return
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        try:
            process = win32api.OpenProcess(0x1000, False, pid)  # query limited
            exe = win32process.GetModuleFileNameEx(process, 0)
        except Exception:  # noqa: BLE001 - another user's or a protected process
            return
        if Path(exe).name.lower() == "sldworks.exe":
            found.append(hwnd)

    win32gui.EnumWindows(_match, None)
    if not found:
        raise RuntimeError("no SolidWorks window")
    hwnd = max(found, key=_area)  # the main window, not a floating toolbar
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    window_dc = win32gui.GetWindowDC(hwnd)
    source = win32ui.CreateDCFromHandle(window_dc)
    memory = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(source, width, height)
    memory.SelectObject(bitmap)
    try:
        # PW_RENDERFULLCONTENT (2) includes the OpenGL graphics area.
        import ctypes

        ctypes.windll.user32.PrintWindow(hwnd, memory.GetSafeHdc(), 2)
        info = bitmap.GetInfo()
        image = Image.frombuffer(
            "RGB",
            (info["bmWidth"], info["bmHeight"]),
            bitmap.GetBitmapBits(True),
            "raw",
            "BGRX",
            0,
            1,
        )
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(hwnd, window_dc)
    return image


def _caption_lines(label: str, payload: Any) -> list[str]:
    """Wrap the label and a readable payload for the caption panel."""
    body = pprint.pformat(payload, width=_CAPTION_WIDTH_CHARS, sort_dicts=False)
    lines = [f"[evidence] {label}"]
    for raw in body.splitlines():
        lines.extend(textwrap.wrap(raw, _CAPTION_WIDTH_CHARS) or [""])
    if len(lines) > _CAPTION_MAX_LINES:
        lines = lines[: _CAPTION_MAX_LINES - 1] + ["..."]
    return lines


def _capture(directory: Path, label: str, payload: Any) -> None:
    """Save the SolidWorks window with the evidence captioned beneath it."""
    from PIL import Image, ImageDraw, ImageFont

    shot = _solidworks_window_image()
    try:
        font = ImageFont.truetype("consola.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    lines = _caption_lines(label, payload)
    line_height = 24
    panel = Image.new("RGB", (shot.width, 16 + line_height * len(lines)), (24, 24, 28))
    draw = ImageDraw.Draw(panel)
    for index, line in enumerate(lines):
        colour = (120, 220, 140) if index == 0 else (230, 230, 230)
        draw.text((12, 8 + index * line_height), line, fill=colour, font=font)
    frame = Image.new("RGB", (shot.width, shot.height + panel.height))
    frame.paste(shot, (0, 0))
    frame.paste(panel, (0, shot.height))

    test = _test_name()
    _FRAMES[test] = _FRAMES.get(test, 0) + 1
    directory.mkdir(parents=True, exist_ok=True)
    frame.save(directory / f"{test}-{_FRAMES[test]:02d}.png", optimize=True)
