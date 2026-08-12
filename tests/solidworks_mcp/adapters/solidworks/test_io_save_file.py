"""Regression tests for ``save_file``'s save-over-own-path data loss.

Passing the document's own path to ``save_file`` used to take the Save-As
branch, which closed the document and deleted the file on disk before calling
``SaveAs3`` on the now-closed document. The result was an empty part and lost
geometry.

These tests drive the adapter with fakes, so they need no SolidWorks.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from solidworks_mcp.adapters.solidworks import io as io_mod


class _FakeModel:
    """Stands in for IModelDoc2, recording which save path was taken."""

    def __init__(self, path: str) -> None:
        self._path = path
        self.save3_calls = 0
        self.save_as3_calls: list[str] = []

    def GetPathName(self) -> str:
        """Return the document's current on-disk path."""
        return self._path

    def Save3(self, options: int, errors: Any, warnings: Any) -> bool:
        """Plain save; leaves the file where it is."""
        self.save3_calls += 1
        return True

    def SaveAs3(self, path: str, version: int, options: int) -> bool:
        """Save-As; writes the document to a new path."""
        self.save_as3_calls.append(path)
        Path(path).write_bytes(b"saved-as geometry")
        return True


class _FakeApp:
    """Stands in for ISldWorks, recording CloseDoc arguments."""

    def __init__(self) -> None:
        self.closed: list[str] = []

    def CloseDoc(self, name: str) -> None:
        """Record the document SolidWorks was asked to close."""
        self.closed.append(name)


class _FakeAdapter:
    """Minimal adapter surface used by SolidWorksIOMixin.save_file."""

    def __init__(self, model: _FakeModel, app: _FakeApp) -> None:
        self.currentModel = model
        self.swApp = app

    def _attempt(self, fn, default=None):
        """Call fn, swallowing failures the way the real adapter does."""
        try:
            return fn()
        except Exception:
            return default

    @staticmethod
    def _get_attr_or_call(obj: Any, name: str) -> Any:
        """Read a member that may be a property or a zero-arg method."""
        member = getattr(obj, name, None)
        return member() if callable(member) else member

    def _handle_com_operation(self, _name: str, operation):
        """Run the operation directly; COM plumbing is not under test here."""
        from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

        try:
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS, data=operation()
            )
        except Exception as exc:
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=str(exc)
            )


def _mixin_for(adapter: _FakeAdapter) -> Any:
    """Bind SolidWorksIOMixin to a fake adapter."""
    mixin = io_mod.SolidWorksIOMixin()
    mixin._adapter = lambda _self: adapter  # type: ignore[method-assign]
    return mixin


@pytest.mark.asyncio
async def test_saving_to_own_path_preserves_the_file(tmp_path: Path) -> None:
    """The regression: saving over the document's own path must not delete it."""
    part = tmp_path / "bracket.sldprt"
    part.write_bytes(b"original geometry")
    original_size = part.stat().st_size

    model = _FakeModel(str(part))
    app = _FakeApp()
    result = await _mixin_for(_FakeAdapter(model, app)).save_file(str(part))

    assert result.is_success, result.error
    # The file must still be there, with its contents intact.
    assert part.exists()
    assert part.read_bytes() == b"original geometry"
    assert part.stat().st_size == original_size

    # It must take the plain-Save path, and must not close the document
    # being saved or Save-As over itself.
    assert model.save3_calls == 1
    assert model.save_as3_calls == []
    assert app.closed == []


@pytest.mark.asyncio
async def test_saving_to_own_path_is_case_and_separator_insensitive(
    tmp_path: Path,
) -> None:
    """Windows paths differing only in case are still the same file."""
    part = tmp_path / "Bracket.SLDPRT"
    part.write_bytes(b"original geometry")

    model = _FakeModel(str(part))
    app = _FakeApp()
    # Same file, spelled differently.
    odd_case = str(part).upper() if os.name == "nt" else str(part)
    result = await _mixin_for(_FakeAdapter(model, app)).save_file(odd_case)

    assert result.is_success, result.error
    assert part.read_bytes() == b"original geometry"
    if os.name == "nt":
        assert model.save3_calls == 1
        assert model.save_as3_calls == []


@pytest.mark.asyncio
async def test_saving_to_a_new_path_still_uses_save_as(tmp_path: Path) -> None:
    """Save-As to a genuinely different path is unaffected by the fix."""
    part = tmp_path / "bracket.sldprt"
    part.write_bytes(b"original geometry")
    target = tmp_path / "copy.sldprt"

    model = _FakeModel(str(part))
    app = _FakeApp()
    result = await _mixin_for(_FakeAdapter(model, app)).save_file(str(target))

    assert result.is_success, result.error
    assert target.exists()
    assert model.save_as3_calls == [str(target)]
    assert model.save3_calls == 0
    # The source document is left alone; only the name occupying the target
    # path is closed.
    assert app.closed == [target.name]
    assert part.read_bytes() == b"original geometry"


@pytest.mark.asyncio
async def test_failed_save_as_leaves_the_existing_target_intact(
    tmp_path: Path,
) -> None:
    """A rejected Save-As must not have already deleted the target."""
    part = tmp_path / "bracket.sldprt"
    part.write_bytes(b"original geometry")
    target = tmp_path / "existing.sldprt"
    target.write_bytes(b"valuable existing file")

    class _RefusingModel(_FakeModel):
        def SaveAs3(self, path: str, version: int, options: int) -> bool:
            """Refuse the save without writing anything."""
            self.save_as3_calls.append(path)
            return False

    model = _RefusingModel(str(part))
    result = await _mixin_for(_FakeAdapter(model, _FakeApp())).save_file(
        str(target)
    )

    assert not result.is_success
    # The old file survives, because nothing is deleted up front.
    assert target.read_bytes() == b"valuable existing file"
