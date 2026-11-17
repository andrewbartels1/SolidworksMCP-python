"""Answer a dialog a running macro left waiting for the user (issue #97).

``RunMacro2`` doesn't return while a macro waits on a dialog (a ``MsgBox``, a
user form, a SolidWorks prompt), and COM calls can't move off the connect
thread to time it out. :class:`DialogWatch` runs beside the call on its own
thread and uses only Win32 window calls, never COM. When a dialog the
SolidWorks process opened stays up longer than the timeout, it reads the
dialog and answers it with the non-committal choice:

- **Cancel**, when the dialog has that button;
- else its **only button**, when it has just one (an OK acknowledgement);
- else, with **no buttons** (a VBA user form), it closes the window.

A dialog with several buttons and no Cancel (Yes/No) is left for the user
and logged: pressing Yes or No could change the model.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Protocol

from loguru import logger

#: Window classes of a message box or common dialog, and of a VBA user form.
DIALOG_CLASSES = frozenset({"#32770", "ThunderDFrame"})
_WM_CLOSE = 0x0010
_WM_COMMAND = 0x0111


@dataclass(frozen=True)
class DialogSeen:
    """A dialog the watch found waiting, and what it did.

    Attributes:
        title: The dialog's title.
        text: Its message, the static texts joined.
        buttons: Its button labels, without ``&``.
        answer: ``"Cancel"``, the single button's label, ``"closed"``, or
            None when it was left for the user.
    """

    title: str
    text: str
    buttons: tuple[str, ...]
    answer: str | None

    def describe(self) -> str:
        """One line: the dialog, its text, and how it was answered."""
        said = f": {self.text!r}" if self.text else ""
        if self.answer is None:
            how = "left open: it has no Cancel and more than one button"
        elif self.answer == "closed":
            how = "closed"
        else:
            how = f"answered {self.answer!r}"
        return f"{self.title!r}{said} ({how})"


class Windows(Protocol):
    """The Win32 window calls the watch makes."""

    def dialogs(self, pid: int) -> list[int]:
        """Visible top-level dialog windows of process ``pid``."""

    def title(self, hwnd: int) -> str:
        """A window's title."""

    def children(self, hwnd: int) -> list[tuple[int, str, str]]:
        """A window's children as ``(hwnd, class name, text)``."""

    def control_id(self, hwnd: int) -> int:
        """A child control's ID."""

    def post(self, hwnd: int, message: int, wparam: int, lparam: int) -> None:
        """Post a message to a window without waiting for it."""


class Win32Windows:
    """:class:`Windows` over ``win32gui`` and ``win32process``.

    Args:
        gui: The ``win32gui`` module; imported when None.
        process: The ``win32process`` module; imported when None.
    """

    def __init__(self, gui: Any = None, process: Any = None) -> None:
        """Keep the two modules."""
        if gui is None or process is None:
            import win32gui
            import win32process

            gui, process = gui or win32gui, process or win32process
        self._gui = gui
        self._process = process

    def dialogs(self, pid: int) -> list[int]:
        """Visible top-level dialog windows of process ``pid``."""
        found: list[int] = []

        def _visit(hwnd: int, _extra: Any) -> bool:
            if (
                self._gui.IsWindowVisible(hwnd)
                and self._gui.GetClassName(hwnd) in DIALOG_CLASSES
                and self._process.GetWindowThreadProcessId(hwnd)[1] == pid
            ):
                found.append(hwnd)
            return True

        self._gui.EnumWindows(_visit, None)
        return found

    def title(self, hwnd: int) -> str:
        """A window's title."""
        return str(self._gui.GetWindowText(hwnd))

    def children(self, hwnd: int) -> list[tuple[int, str, str]]:
        """A window's children as ``(hwnd, class name, text)``."""
        kids: list[tuple[int, str, str]] = []

        def _visit(child: int, _extra: Any) -> bool:
            kids.append(
                (child, self._gui.GetClassName(child), self._gui.GetWindowText(child))
            )
            return True

        self._gui.EnumChildWindows(hwnd, _visit, None)
        return kids

    def control_id(self, hwnd: int) -> int:
        """A child control's ID."""
        return int(self._gui.GetDlgCtrlID(hwnd))

    def post(self, hwnd: int, message: int, wparam: int, lparam: int) -> None:
        """Post a message to a window without waiting for it."""
        self._gui.PostMessage(hwnd, message, wparam, lparam)


@dataclass
class DialogWatch:
    """Watch process ``pid`` for a dialog left waiting, while a call runs.

    Use it as a context manager around the blocking call. Dialogs already
    open when it starts are ignored.

    Attributes:
        pid: The SolidWorks process ID.
        timeout: Seconds a dialog may stay open before it is answered.
        windows: The window calls; the real Win32 ones by default.
        poll: Seconds between looks.
        clock: The time source, in seconds.
        seen: Every dialog answered or left, in the order found.
    """

    pid: int
    timeout: float
    windows: Windows = field(default_factory=Win32Windows)
    poll: float = 0.5
    clock: Callable[[], float] = time.monotonic
    seen: list[DialogSeen] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Set up the thread state."""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._before: set[int] = set()
        self._first: dict[int, float] = {}
        self._handled: set[int] = set()

    def __enter__(self) -> DialogWatch:
        """Note the dialogs already open and start watching."""
        self._before = set(self.windows.dialogs(self.pid))
        self._thread = threading.Thread(
            target=self._run, name="macro-dialog-watch", daemon=True
        )
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stop watching."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Look every ``poll`` seconds until stopped; a failure ends the watch."""
        try:
            while not self._stop.wait(self.poll):
                self.check()
        except Exception as exc:  # noqa: BLE001 - a watch never fails the macro
            logger.warning("[macro] the dialog watch stopped: {}", exc)

    def check(self) -> None:
        """Answer any new dialog that has been open longer than the timeout."""
        now = self.clock()
        for hwnd in self.windows.dialogs(self.pid):
            if hwnd in self._before or hwnd in self._handled:
                continue
            opened = self._first.setdefault(hwnd, now)
            if now - opened >= self.timeout:
                self._handled.add(hwnd)
                self._answer(hwnd)

    def _answer(self, hwnd: int) -> None:
        """Read one dialog and answer it with the non-committal choice."""
        kids = self.windows.children(hwnd)
        text = " ".join(
            t.strip() for _h, cls, t in kids if cls == "Static" and t.strip()
        )
        buttons = [
            (h, t.replace("&", "").strip()) for h, cls, t in kids if cls == "Button"
        ]
        labels = tuple(label for _h, label in buttons)
        cancel = [h for h, label in buttons if label.lower() == "cancel"]
        answer: str | None
        if cancel or len(buttons) == 1:
            button = cancel[0] if cancel else buttons[0][0]
            answer = "Cancel" if cancel else buttons[0][1]
            # The button's own click: WM_COMMAND with its ID (BN_CLICKED is 0).
            self.windows.post(
                hwnd, _WM_COMMAND, self.windows.control_id(button), button
            )
        elif not buttons:
            answer = "closed"
            self.windows.post(hwnd, _WM_CLOSE, 0, 0)
        else:
            answer = None
        seen = DialogSeen(self.windows.title(hwnd), text, labels, answer)
        self.seen.append(seen)
        if answer is None:
            logger.warning("[macro] a dialog needs the user: {}", seen.describe())
        else:
            logger.warning("[macro] a dialog was waiting: {}", seen.describe())


def waited_message(seen: list[DialogSeen], timeout: float) -> str:
    """The error for a macro that waited on dialogs.

    Args:
        seen: The dialogs the watch found.
        timeout: The timeout that was used, in seconds.

    Returns:
        str: What happened, and that macros here must not wait for the user.
    """
    dialogs = "; ".join(d.describe() for d in seen)
    return (
        f"The macro waited for the user: after {timeout:g} s a dialog was still "
        f"open, {dialogs}. It may have done part of its work before that. "
        "Macros run by execute_macro must not wait for the user: remove the "
        "MsgBox, form or prompt, or raise dialog_timeout."
    )
