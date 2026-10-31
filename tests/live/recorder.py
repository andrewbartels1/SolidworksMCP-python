"""Record the SolidWorks window during a live demo, keeping only frames that changed.

With ``SW_DEMO_RECORD`` set, the ``_record_demo`` fixture in
``tests/live/conftest.py`` starts a :class:`Recorder` for each test. A
background thread grabs the SolidWorks window's screen pixels up to
``SW_DEMO_RECORD_FPS`` times a second (default 12) and saves a frame only when
the picture changed, named by its time in milliseconds. ``evidence()`` stamps
its caption into the same folder, so ``tests/scripts/make_demo_gif.py
--recording`` can build a GIF whose frame rate follows the motion: a feature
redrawing plays frame by frame, a still stretch is one frame.

The recorder never calls SolidWorks. ``ImageGrab`` copies what is on the
screen, so SolidWorks must be in front and unobscured while recording (the
stills use ``PrintWindow``, which works when covered but sends the window a
message every time - too much at 12 a second for SolidWorks 2026, COM pitfall
#26).

Files, under ``<SW_DEMO_CAPTURE_DIR>/recording/<test>/`` (or
``tests/.generated/recordings/<test>/`` without a capture directory):

- ``frame-<ms>.png``: a changed frame, ``ms`` after the recording started;
- ``caption-<ms>.png``: an evidence caption panel, shown from then on;
- ``end-<ms>``: when the recording stopped.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any

#: The running recorder, if any; ``evidence()`` stamps captions into it.
_ACTIVE: Recorder | None = None

#: Frames are compared at this width; a grey level change above
#: ``_CHANGE_LEVEL`` anywhere counts as a change.
_COMPARE_WIDTH = 320
_CHANGE_LEVEL = 24


class Recorder:
    """Grab the SolidWorks window on a thread, keeping frames that changed."""

    def __init__(self, directory: Path, fps: float) -> None:
        self.directory = directory
        self.interval = 1.0 / max(fps, 0.5)
        self.frames = 0
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: Any = None
        self._started = 0.0
        self._width = 0

    def _ms(self) -> int:
        """Milliseconds since the recording started."""
        return int((time.monotonic() - self._started) * 1000)

    def start(self) -> None:
        """Clear the folder and start grabbing."""
        shutil.rmtree(self.directory, ignore_errors=True)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._started = time.monotonic()
        self._thread = threading.Thread(
            target=self._run, name="demo-recorder", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop grabbing and mark the end time."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        (self.directory / f"end-{self._ms():08d}").touch()

    def caption(self, label: str, payload: Any, call: str | None) -> None:
        """Save an evidence caption, shown under every frame from now on."""
        from tests.live.evidence import caption_panel

        width = self._width or 1280
        panel = caption_panel(width, label, payload, call)
        panel.save(self.directory / f"caption-{self._ms():08d}.png")

    def _run(self) -> None:
        """Grab, compare and save until stopped; a failure ends the recording."""
        try:
            from tests.live.evidence import solidworks_window

            hwnd = solidworks_window()
            while not self._stop.is_set():
                began = time.monotonic()
                self._keep_if_changed(self._grab(hwnd))
                self._stop.wait(max(0.0, self.interval - (time.monotonic() - began)))
        except Exception as exc:  # noqa: BLE001 - a recording never fails a test
            self.error = f"{type(exc).__name__}: {exc}"
            print(f"[recorder] stopped: {self.error}", flush=True)

    def _grab(self, hwnd: int) -> Any:
        """The window's pixels as they are on the screen."""
        import win32gui
        from PIL import ImageGrab

        bbox = win32gui.GetWindowRect(hwnd)
        return ImageGrab.grab(bbox=bbox, all_screens=True)

    def _keep_if_changed(self, image: Any) -> None:
        """Save ``image`` when it differs from the last frame kept."""
        from PIL import ImageChops

        height = max(1, round(image.height * _COMPARE_WIDTH / image.width))
        small = image.convert("L").resize((_COMPARE_WIDTH, height))
        if self._last is not None and self._last.size == small.size:
            diff = ImageChops.difference(small, self._last)
            if diff.point(lambda v: 255 if v > _CHANGE_LEVEL else 0).getbbox() is None:
                return
        self._last = small
        self._width = image.width
        image.save(self.directory / f"frame-{self._ms():08d}.png", compress_level=1)
        self.frames += 1


def _directory(test: str) -> Path:
    """Where ``test``'s recording goes."""
    capture = os.getenv("SW_DEMO_CAPTURE_DIR")
    base = Path(capture) if capture else Path("tests/.generated/recordings")
    return base / "recording" / test if capture else base / test


def asked() -> bool:
    """Whether ``SW_DEMO_RECORD`` asks for a recording."""
    return os.getenv("SW_DEMO_RECORD", "").lower() in {"1", "true", "yes"}


def start_if_asked(test: str) -> Recorder | None:
    """Start recording ``test`` when ``SW_DEMO_RECORD`` is set."""
    global _ACTIVE
    if not asked():
        return None
    try:
        fps = float(os.getenv("SW_DEMO_RECORD_FPS", "12"))
    except ValueError:
        fps = 12.0
    _ACTIVE = Recorder(_directory(test), fps)
    _ACTIVE.start()
    return _ACTIVE


def stop(recorder: Recorder) -> None:
    """Stop ``recorder`` and report what it kept."""
    global _ACTIVE
    recorder.stop()
    if _ACTIVE is recorder:
        _ACTIVE = None
    print(f"[recorder] {recorder.frames} frames in {recorder.directory}", flush=True)


def note_caption(label: str, payload: Any, call: str | None) -> None:
    """Stamp an evidence caption into the running recording, if there is one."""
    if _ACTIVE is None:
        return
    try:
        _ACTIVE.caption(label, payload, call)
    except Exception as exc:  # noqa: BLE001 - a recording never fails a test
        print(f"[recorder] caption skipped: {exc}", flush=True)
