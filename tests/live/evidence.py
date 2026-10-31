"""Print a live test's proof, and hold SolidWorks on it during a demo.

``evidence(label, payload, call=...)`` prints ``[evidence] <label>``, the
tool call that produced the payload (``call``, when given) and the payload,
coloured with ``rich`` (what ``tests/scripts/live_demo.ps1`` shows). When
``SW_DEMO_HOLD_SECONDS`` is set
it then pauses, so a person watching SolidWorks sees the state the line
proves before the test moves on or closes its documents. Normal live runs
leave it unset and are not slowed.

When ``SW_DEMO_CAPTURE_DIR`` is set, each line also saves a PNG of the
SolidWorks window with the label, call and payload captioned beneath it in
terminal colours, named ``<test>-<NN>.png``. ``tests/scripts/make_demo_gif.py`` turns one test's
frames into a GIF for a pull request or the docs. The capture copies the
window's pixels (``PrintWindow``); it makes no SolidWorks API call.

When a recording is running (``SW_DEMO_RECORD``, see ``tests/live/recorder.py``)
each line's caption is also stamped into it, so the recorded frames carry it.
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
_CAPTION_MAX_LINES = 12
#: Caption text size in pixels: large enough to read once a frame is scaled
#: down to README width.
_CAPTION_FONT_SIZE = 30
_CAPTION_LINE_HEIGHT = 40
#: A window narrower than this (SolidWorks minimised, or only its title bar
#: found) is left out: the frame is the caption alone, at this width.
_MIN_FRAME_WIDTH = 1280

#: Caption colours (VS Code Dark+): pygments token type -> RGB.
_BACKGROUND = (24, 24, 28)
_HEADER = (120, 220, 140)
_TAG = (78, 201, 176)
_TEXT = (212, 212, 212)
_TOKEN_COLOURS = {
    "Literal.String": (206, 145, 120),
    "Literal.Number": (181, 206, 168),
    "Keyword": (86, 156, 214),
    "Name.Builtin": (86, 156, 214),
    "Name": (156, 220, 254),
    "Operator": (212, 212, 212),
    "Punctuation": (212, 212, 212),
}


def evidence(
    label: str,
    payload: Any,
    call: str | None = None,
    picture: Any = None,
    quick: bool = False,
) -> None:
    """Print one proof, hold if asked, then capture it if asked.

    The capture comes after the hold so SolidWorks has finished redrawing the
    state the line proves.

    Args:
        label: What the payload proves.
        payload: The tool's result, or what was read back.
        call: The tool call that produced it, e.g.
            ``'arrange_dimensions({"view_name": None})'``.
        picture: A PIL image framed instead of the SolidWorks window, e.g. an
            exported PDF's page from :func:`pdf_page`.
        quick: Print it only: no caption in a recording, no hold and no
            still, for a run of small steps the recording shows as motion.
    """
    _print(label, payload, call)
    from tests.live import recorder

    if quick:
        return
    recorder.note_caption(label, payload, call)
    try:
        hold = float(os.getenv("SW_DEMO_HOLD_SECONDS", "0"))
    except ValueError:
        hold = 0.0
    if hold > 0:
        time.sleep(hold)
    capture_dir = os.getenv("SW_DEMO_CAPTURE_DIR")
    if capture_dir:
        try:
            _capture(Path(capture_dir), label, payload, call, picture)
        except Exception as exc:  # noqa: BLE001 - a picture never fails a test
            print(f"[evidence] (capture skipped: {exc})", flush=True)


def starting(label: str, call: str | None = None) -> None:
    """Caption a recording as a step starts, so its motion plays under it.

    ``evidence`` captions a step once it has finished; without this, whatever
    SolidWorks draws while a step runs plays under the previous step's
    caption. Does nothing unless a recording is running.
    """
    from tests.live import recorder

    recorder.note_caption(label, "running ...", call)


def _print(label: str, payload: Any, call: str | None) -> None:
    """Print the proof in colour; plain text when ``rich`` is missing."""
    try:
        from rich.console import Console
        from rich.markup import escape
        from rich.pretty import Pretty
        from rich.text import Text
    except ImportError:
        call_text = f" {call} ->" if call else ""
        print(f"\n[evidence] {label}:{call_text} {payload}", flush=True)
        return
    console = Console(force_terminal=True, highlight=True, width=_CAPTION_WIDTH_CHARS)
    console.print()
    console.print(f"[bold green]\\[evidence][/] [bold]{escape(label)}[/]")
    if call:
        console.print(Text("call   ", style="bold cyan"), call, sep="")
        console.print(Text("result", style="bold cyan"))
    console.print(Pretty(payload))


def _test_name() -> str:
    """The running test's function name, from ``PYTEST_CURRENT_TEST``."""
    current = os.getenv("PYTEST_CURRENT_TEST", "demo").split(" ")[0]
    return re.sub(r"[^\w-]+", "_", current.split("::")[-1]).strip("_") or "demo"


def _area(hwnd: int) -> int:
    """A window's on-screen area in pixels."""
    import win32gui

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return (right - left) * (bottom - top)


def solidworks_window() -> int:
    """The SolidWorks main window's handle.

    The window is the largest one owned by ``sldworks.exe``. A title match
    also caught an editor with this repo open ("SolidworksMCP-python - Visual
    Studio Code") and captured it whenever it was in front.
    """
    import win32api
    import win32gui
    import win32process

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
    return int(max(found, key=_area))  # the main window, not a floating toolbar


def _solidworks_window_image() -> Any:
    """Copy the SolidWorks main window's pixels, even if it is covered."""
    import win32gui
    import win32ui
    from PIL import Image

    hwnd = solidworks_window()
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


def _caption_lines(
    label: str, payload: Any, call: str | None = None, chars: int = _CAPTION_WIDTH_CHARS
) -> list[tuple[str, str]]:
    """Wrap the label, call and a readable payload for the caption panel.

    Returns:
        list[tuple[str, str]]: ``(kind, text)`` lines; ``kind`` is ``header``,
        ``call``, ``call more`` (a long call's next line), ``tag`` or
        ``code`` and picks the colouring.
    """
    lines = [("header", f"[evidence] {label}")]
    if call:
        wrapped = textwrap.wrap(call, chars - 7) or [call]
        lines.append(("call", wrapped[0]))
        lines.extend(("call more", w) for w in wrapped[1:])
        lines.append(("tag", "result"))
    body = pprint.pformat(payload, width=chars, sort_dicts=False)
    for raw in body.splitlines():
        lines.extend(("code", w) for w in textwrap.wrap(raw, chars))
    if len(lines) > _CAPTION_MAX_LINES:
        lines = lines[: _CAPTION_MAX_LINES - 1] + [("tag", "...")]
    return lines


def _token_colour(token: Any) -> tuple[int, int, int]:
    """Caption colour of a pygments token type (its nearest listed parent)."""
    while token is not None:
        colour = _TOKEN_COLOURS.get(str(token).removeprefix("Token."))
        if colour:
            return colour
        token = token.parent
    return _TEXT


def _draw_code(draw: Any, x: float, y: int, text: str, font: Any) -> None:
    """Draw one line of Python with syntax colours."""
    from pygments.lexers import PythonLexer

    for token, value in PythonLexer().get_tokens(text):
        value = value.rstrip("\n")
        if value:
            draw.text((x, y), value, fill=_token_colour(token), font=font)
            x += draw.textlength(value, font=font)


def caption_panel(width: int, label: str, payload: Any, call: str | None) -> Any:
    """The evidence caption drawn as a dark panel ``width`` pixels wide."""
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype("consola.ttf", _CAPTION_FONT_SIZE)
        bold = ImageFont.truetype("consolab.ttf", _CAPTION_FONT_SIZE)
    except OSError:
        font = bold = ImageFont.load_default()
    # Consolas is 0.55 em wide: wrap at what fits across the panel.
    chars = max(40, int((width - 24) / (0.55 * _CAPTION_FONT_SIZE)))
    lines = _caption_lines(label, payload, call, chars)
    height = 16 + _CAPTION_LINE_HEIGHT * len(lines)
    panel = Image.new("RGB", (width, height), _BACKGROUND)
    draw = ImageDraw.Draw(panel)
    for index, (kind, text) in enumerate(lines):
        y = 8 + index * _CAPTION_LINE_HEIGHT
        if kind == "header":
            draw.text((12, y), text, fill=_HEADER, font=bold)
        elif kind == "tag":
            draw.text((12, y), text, fill=_TAG, font=bold)
        elif kind == "call":
            draw.text((12, y), "call", fill=_TAG, font=bold)
            _draw_code(draw, 12 + draw.textlength("call   ", font=font), y, text, font)
        elif kind == "call more":
            _draw_code(draw, 12 + draw.textlength("call   ", font=font), y, text, font)
        else:
            _draw_code(draw, 12, y, text, font)
    return panel


def pdf_page(path: str | Path, width: int = 1800) -> Any:
    """The first page of a PDF as a PIL image ``width`` pixels wide (pypdfium2)."""
    import pypdfium2

    pdf = pypdfium2.PdfDocument(str(path))
    try:
        page = pdf[0]
        return page.render(scale=width / page.get_width()).to_pil().convert("RGB")
    finally:
        pdf.close()


def _capture(
    directory: Path, label: str, payload: Any, call: str | None, picture: Any = None
) -> None:
    """Save the SolidWorks window (or ``picture``) with the evidence beneath it."""
    from PIL import Image

    shot = picture if picture is not None else _solidworks_window_image()
    if shot.width < _MIN_FRAME_WIDTH:
        shot = Image.new("RGB", (_MIN_FRAME_WIDTH, 0))
    panel = caption_panel(shot.width, label, payload, call)
    frame = Image.new("RGB", (shot.width, shot.height + panel.height))
    frame.paste(shot, (0, 0))
    frame.paste(panel, (0, shot.height))

    test = _test_name()
    _FRAMES[test] = _FRAMES.get(test, 0) + 1
    directory.mkdir(parents=True, exist_ok=True)
    frame.save(directory / f"{test}-{_FRAMES[test]:02d}.png", optimize=True)
