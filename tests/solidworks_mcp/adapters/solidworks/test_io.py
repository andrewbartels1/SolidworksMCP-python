"""Tests for SolidWorks IO mixin behaviors."""

from __future__ import annotations

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
