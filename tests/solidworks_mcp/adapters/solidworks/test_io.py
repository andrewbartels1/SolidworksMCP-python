"""Tests for SolidWorks IO mixin behaviors."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import io as _io_module
from solidworks_mcp.adapters.solidworks.io import (
    SolidWorksIOMixin,
    _get_sw_comtypes_lib,
)


class _IOHarness(SolidWorksIOMixin):
    """Minimal harness for IO mixin."""

    def __init__(self, current_model, sw_app=None, session_docs=None) -> None:
        self.currentModel = current_model
        self.swApp = sw_app
        self._session_docs = session_docs if session_docs is not None else []

    def _attempt(self, callback, default=None):
        try:
            return callback()
        except Exception:
            return default

    def _get_attr_or_call(self, obj, attr_name):
        attr = getattr(obj, attr_name, None)
        return attr() if callable(attr) else attr

    def _handle_com_operation(self, _name, callback, *args):
        try:
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=callback())
        except Exception as exc:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(exc))

    def is_connected(self) -> bool:
        return self.swApp is not None


import pytest


@pytest.mark.asyncio
async def test_get_mass_properties_uses_callable_gmp() -> None:
    """Callable GetMassProperties should be used when CreateMassProperty is missing."""
    # Provide a callable GetMassProperties to cover the callable branch.
    current_model = SimpleNamespace(
        ForceRebuild3=lambda _flag: None,
        Extension=SimpleNamespace(CreateMassProperty=lambda: None),
        GetMassProperties=lambda: [1.0, 2.0, 3.0, 0.1, 0.2, 0.3],
    )
    harness = _IOHarness(current_model)
    result = await harness.get_mass_properties()
    assert result.is_success
    assert result.data.mass == 0.3


@pytest.mark.asyncio
async def test_get_mass_properties_missing_gmp_fails() -> None:
    """Missing GetMassProperties should surface a failure."""
    # Use a non-callable/non-list attribute to hit raw=None.
    current_model = SimpleNamespace(
        ForceRebuild3=lambda _flag: None,
        Extension=SimpleNamespace(CreateMassProperty=lambda: None),
        GetMassProperties=123,
    )
    harness = _IOHarness(current_model)
    result = await harness.get_mass_properties()
    assert result.status == AdapterResultStatus.ERROR
    assert "Failed to get mass properties" in (result.error or "")


def test_get_sw_comtypes_lib_returns_cached_value() -> None:
    """Second call returns the cached module without re-querying the registry (io.py:46-47)."""
    sentinel = object()
    with patch.object(_io_module, "_sw_comtypes_lib", sentinel):
        result = _get_sw_comtypes_lib()
    assert result is sentinel


def test_get_sw_comtypes_lib_returns_none_when_comtypes_unavailable() -> None:
    """Returns None immediately when comtypes is not installed (io.py:48-49)."""
    with (
        patch.object(_io_module, "_sw_comtypes_lib", None),
        patch.object(_io_module, "_COMTYPES_AVAILABLE", False),
    ):
        result = _get_sw_comtypes_lib()
    assert result is None


def _fake_doc(title: str, *, dirty: bool = False, on_close=None) -> SimpleNamespace:
    """Build a SimpleNamespace standing in for a SolidWorks document."""
    return SimpleNamespace(
        GetTitle=lambda: title,
        GetSaveFlag=lambda: dirty,
        _on_close=on_close,
    )


@pytest.mark.asyncio
async def test_close_model_discards_changes_without_saving() -> None:
    """close_model(save=False) closes the active doc without calling Save."""
    closed_titles: list[str] = []
    doc = _fake_doc("Part1", dirty=False)
    sw_app = SimpleNamespace(CloseDoc=lambda title: closed_titles.append(title))
    harness = _IOHarness(current_model=doc, sw_app=sw_app, session_docs=[doc])

    result = await harness.close_model(save=False)

    assert result.is_success
    assert closed_titles == ["Part1"]
    assert harness.currentModel is None
    assert harness._session_docs == []


@pytest.mark.asyncio
async def test_close_all_session_docs_closes_only_session_tracked_documents() -> None:
    """Only documents this session opened/created get closed - never a blanket sweep.

    Regression guard: close_all_session_docs must NOT use
    ISldWorks.GetDocuments() (closing every open document in the shared
    SolidWorks instance), since that would also close documents the user
    opened by hand outside of this automation session.
    """
    closed_titles: list[str] = []
    docs = [_fake_doc("Part1"), _fake_doc("Assem1"), _fake_doc("Drawing1")]
    user_doc = _fake_doc("UsersOwnFile")
    sw_app = SimpleNamespace(
        # Deliberately no GetDocuments - if the implementation calls it,
        # this test fails loudly instead of silently closing everything.
        CloseDoc=lambda title: closed_titles.append(title),
    )
    harness = _IOHarness(current_model=docs[0], sw_app=sw_app, session_docs=list(docs))

    result = await harness.close_all_session_docs()

    assert result.is_success
    assert result.data["closed"] == ["Part1", "Assem1", "Drawing1"]
    assert result.data["failed"] == {}
    assert harness.currentModel is None
    assert harness._session_docs == []
    assert user_doc.GetTitle() not in closed_titles


@pytest.mark.asyncio
async def test_close_all_session_docs_records_failures_without_aborting() -> None:
    """A failure closing one document doesn't prevent closing the rest."""

    def _close_doc(title: str) -> None:
        if title == "Broken":
            raise Exception("RPC server unavailable")

    docs = [_fake_doc("Broken"), _fake_doc("Fine")]
    sw_app = SimpleNamespace(CloseDoc=_close_doc)
    harness = _IOHarness(current_model=None, sw_app=sw_app, session_docs=list(docs))

    result = await harness.close_all_session_docs()

    assert result.is_success
    assert result.data["closed"] == ["Fine"]
    assert "Broken" in result.data["failed"]


@pytest.mark.asyncio
async def test_create_part_tracks_the_new_document_for_session_close() -> None:
    """create_part() must record the new doc so close_all_session_docs finds it."""
    new_doc = _fake_doc("Part1")
    sw_app = SimpleNamespace(NewPart=lambda: new_doc)
    harness = _IOHarness(current_model=None, sw_app=sw_app)

    result = await harness.create_part()

    assert result.is_success
    assert harness._session_docs == [new_doc]


@pytest.mark.asyncio
async def test_open_model_does_not_duplicate_an_already_tracked_document() -> None:
    """Re-opening the same live doc object must not double-track it."""
    doc = _fake_doc("Part1")
    harness = _IOHarness(current_model=None, sw_app=SimpleNamespace())

    harness._track_session_doc(harness, doc)
    harness._track_session_doc(harness, doc)

    assert harness._session_docs == [doc]


@pytest.mark.asyncio
async def test_close_all_session_docs_empty_when_nothing_tracked() -> None:
    """No session-tracked documents means nothing to close, not an error."""
    sw_app = SimpleNamespace(CloseDoc=lambda title: None)
    harness = _IOHarness(current_model=None, sw_app=sw_app)

    result = await harness.close_all_session_docs()

    assert result.is_success
    assert result.data == {"closed": [], "failed": {}}


@pytest.mark.asyncio
async def test_close_all_session_docs_requires_connected_app() -> None:
    """Without a live swApp, close_all_session_docs reports an error instead of crashing."""
    harness = _IOHarness(current_model=None, sw_app=None)

    result = await harness.close_all_session_docs()

    assert result.status == AdapterResultStatus.ERROR
    assert "not connected" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_close_model_treats_save_flag_error_as_not_dirty() -> None:
    """GetSaveFlag() raising is treated as not-dirty, not propagated (io.py:210-211)."""

    def _raise() -> bool:
        raise RuntimeError("COM error")

    doc = SimpleNamespace(GetTitle=lambda: "Part1", GetSaveFlag=_raise)
    closed_titles: list[str] = []
    sw_app = SimpleNamespace(CloseDoc=lambda title: closed_titles.append(title))
    harness = _IOHarness(current_model=doc, sw_app=sw_app, session_docs=[doc])

    result = await harness.close_model(save=False)

    assert result.is_success
    assert closed_titles == ["Part1"]


@pytest.mark.asyncio
async def test_close_model_starts_and_joins_watcher_when_dirty(monkeypatch) -> None:
    """A dirty document starts the save-prompt watcher thread and joins it
    before returning (io.py:216-219, 225)."""
    watched: list[tuple] = []

    def _fake_watch(stop_event, timeout: float = 5.0) -> None:
        watched.append((stop_event, timeout))

    monkeypatch.setattr(_io_module, "_watch_for_save_prompt", _fake_watch)

    doc = _fake_doc("Part1", dirty=True)
    sw_app = SimpleNamespace(CloseDoc=lambda title: None)
    harness = _IOHarness(current_model=doc, sw_app=sw_app, session_docs=[doc])

    result = await harness.close_model(save=False)

    assert result.is_success
    assert len(watched) == 1


def test_track_session_doc_initializes_missing_session_docs_list() -> None:
    """When ``_session_docs`` isn't set at all, it's created fresh (io.py:305-306)."""

    class _BareAdapter:
        pass

    bare = _BareAdapter()
    doc = object()

    SolidWorksIOMixin._track_session_doc(bare, doc)

    assert bare._session_docs == [doc]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_save_file_same_path_falls_back_to_save_and_raises_if_missing(
    tmp_path,
) -> None:
    """same_file branch: Save3 unavailable falls back to Save(); missing file still raises."""
    target = tmp_path / "part.sldprt"
    model = SimpleNamespace(
        GetTitle=lambda: "Part1",
        GetPathName=lambda: str(target),
        Save=lambda: None,
    )
    harness = _IOHarness(current_model=model, sw_app=SimpleNamespace())

    result = await harness.save_file(str(target))

    assert result.status == AdapterResultStatus.ERROR
    assert "File not written after save" in (result.error or "")


# ---------------------------------------------------------------------------
# Win32 dialog-dismissal helpers (_win_text, _win_class,
# _find_and_dismiss_save_prompt, _watch_for_save_prompt).
#
# These wrap ctypes.WinDLL("user32") calls behind the module-level
# ``_USER32`` object, so the Win32 API surface can be faked out entirely -
# the dialog-hunting/button-matching logic underneath is pure Python.
# ---------------------------------------------------------------------------


class _FakeUser32:
    """Simulate the subset of user32 EnumWindows/EnumChildWindows this module uses."""

    def __init__(self) -> None:
        self.texts: dict[int, str] = {}
        self.classes: dict[int, str] = {}
        self.visible: dict[int, bool] = {}
        self.top_level: list[int] = []
        self.children: dict[int, list[int]] = {}
        self.clicked: list[int] = []

    def GetWindowTextLengthW(self, hwnd: int) -> int:
        return len(self.texts.get(hwnd, ""))

    def GetWindowTextW(self, hwnd: int, buf, _length: int) -> None:
        buf.value = self.texts.get(hwnd, "")

    def GetClassNameW(self, hwnd: int, buf, _size: int) -> None:
        buf.value = self.classes.get(hwnd, "")

    def IsWindowVisible(self, hwnd: int) -> bool:
        return self.visible.get(hwnd, True)

    def EnumWindows(self, callback, lparam: int) -> int:
        for hwnd in list(self.top_level):
            if not callback(hwnd, lparam):
                break
        return 1

    def EnumChildWindows(self, hwnd: int, callback, lparam: int) -> int:
        for child in list(self.children.get(hwnd, [])):
            if not callback(child, lparam):
                break
        return 1

    def SendMessageW(self, hwnd: int, _msg: int, _wparam: int, _lparam: int) -> int:
        self.clicked.append(hwnd)
        return 0


def test_win_text_returns_empty_string_when_length_is_zero(monkeypatch) -> None:
    fake = _FakeUser32()
    monkeypatch.setattr(_io_module, "_USER32", fake)
    assert _io_module._win_text(1) == ""


def test_win_text_returns_buffer_value(monkeypatch) -> None:
    fake = _FakeUser32()
    fake.texts[1] = "Don't Save"
    monkeypatch.setattr(_io_module, "_USER32", fake)
    assert _io_module._win_text(1) == "Don't Save"


def test_win_class_returns_class_name(monkeypatch) -> None:
    fake = _FakeUser32()
    fake.classes[1] = "#32770"
    monkeypatch.setattr(_io_module, "_USER32", fake)
    assert _io_module._win_class(1) == "#32770"


def test_find_and_dismiss_save_prompt_clicks_matching_button(monkeypatch) -> None:
    fake = _FakeUser32()
    fake.top_level = [100]
    fake.classes[100] = "#32770"
    fake.visible[100] = True
    fake.children[100] = [101]
    fake.classes[101] = "Button"
    fake.texts[101] = "&No"
    monkeypatch.setattr(_io_module, "_USER32", fake)

    assert _io_module._find_and_dismiss_save_prompt() is True
    assert fake.clicked == [101]


def test_find_and_dismiss_save_prompt_returns_false_without_matching_button(
    monkeypatch,
) -> None:
    fake = _FakeUser32()
    fake.top_level = [100]
    fake.classes[100] = "#32770"
    fake.visible[100] = True
    fake.children[100] = [101]
    fake.classes[101] = "Button"
    fake.texts[101] = "Cancel"
    monkeypatch.setattr(_io_module, "_USER32", fake)

    assert _io_module._find_and_dismiss_save_prompt() is False
    assert fake.clicked == []


def test_find_and_dismiss_save_prompt_ignores_non_dialog_windows(monkeypatch) -> None:
    fake = _FakeUser32()
    fake.top_level = [200]
    fake.classes[200] = "Notepad"
    fake.visible[200] = True
    monkeypatch.setattr(_io_module, "_USER32", fake)

    assert _io_module._find_and_dismiss_save_prompt() is False


def test_find_and_dismiss_save_prompt_ignores_invisible_dialog(monkeypatch) -> None:
    fake = _FakeUser32()
    fake.top_level = [100]
    fake.classes[100] = "#32770"
    fake.visible[100] = False
    monkeypatch.setattr(_io_module, "_USER32", fake)

    assert _io_module._find_and_dismiss_save_prompt() is False


def test_find_and_dismiss_save_prompt_moves_on_from_unmatched_dialog(
    monkeypatch,
) -> None:
    """A dialog with no matching button doesn't stop the search for the next one."""
    fake = _FakeUser32()
    fake.top_level = [100, 200]
    fake.classes[100] = "#32770"
    fake.visible[100] = True
    fake.children[100] = [101]
    fake.classes[101] = "Button"
    fake.texts[101] = "Cancel"

    fake.classes[200] = "#32770"
    fake.visible[200] = True
    fake.children[200] = [201]
    fake.classes[201] = "Button"
    fake.texts[201] = "Don't Save"
    monkeypatch.setattr(_io_module, "_USER32", fake)

    assert _io_module._find_and_dismiss_save_prompt() is True
    assert fake.clicked == [201]


def test_watch_for_save_prompt_returns_immediately_without_user32(monkeypatch) -> None:
    monkeypatch.setattr(_io_module, "_USER32", None)
    stop_event = threading.Event()

    _io_module._watch_for_save_prompt(stop_event, timeout=5.0)


def test_watch_for_save_prompt_returns_as_soon_as_dialog_is_dismissed(
    monkeypatch,
) -> None:
    fake = _FakeUser32()
    monkeypatch.setattr(_io_module, "_USER32", fake)
    monkeypatch.setattr(_io_module, "_find_and_dismiss_save_prompt", lambda: True)
    stop_event = threading.Event()

    start = time.monotonic()
    _io_module._watch_for_save_prompt(stop_event, timeout=5.0)

    assert time.monotonic() - start < 1.0


def test_watch_for_save_prompt_polls_until_timeout_elapses(monkeypatch) -> None:
    fake = _FakeUser32()
    monkeypatch.setattr(_io_module, "_USER32", fake)
    monkeypatch.setattr(_io_module, "_find_and_dismiss_save_prompt", lambda: False)
    stop_event = threading.Event()

    start = time.monotonic()
    _io_module._watch_for_save_prompt(stop_event, timeout=0.05)

    assert time.monotonic() - start < 2.0
