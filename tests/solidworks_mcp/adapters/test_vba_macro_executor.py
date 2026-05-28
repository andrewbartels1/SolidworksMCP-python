"""Tests for VbaMacroExecutor behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from solidworks_mcp.adapters.base import AdapterResultStatus
from solidworks_mcp.adapters.vba_macro_executor import MacroExecutionRequest, VbaMacroExecutor


@pytest.mark.asyncio
async def test_execute_macro_records_error_on_exception(monkeypatch, tmp_path) -> None:
    """execute_macro should return error AdapterResult when execution fails."""
    # Force _execute_via_adapter to raise and assert error result.
    executor = VbaMacroExecutor(temp_macro_dir=tmp_path)
    monkeypatch.setattr(executor, "_execute_via_adapter", lambda **_kw: (_ for _ in ()).throw(RuntimeError("boom")))

    request = MacroExecutionRequest(macro_code="code", macro_name="Macro")
    result = await executor.execute_macro(request, backing_adapter=SimpleNamespace())

    assert result.status == AdapterResultStatus.ERROR
    assert "macro execution failed" in (result.error or "")


def test_get_execution_history_with_name() -> None:
    """get_execution_history should return named history when present."""
    # Populate history and verify lookup for a named macro.
    executor = VbaMacroExecutor()
    executor._execution_history["Macro"] = SimpleNamespace(success=True)
    assert "Macro" in executor.get_execution_history("Macro")
    assert executor.get_execution_history("Missing") == {}


@pytest.mark.asyncio
async def test_execute_via_adapter_requires_execute_macro() -> None:
    """Missing execute_macro should return a failure dict."""
    # Cover the missing-method guard.
    executor = VbaMacroExecutor()
    result = await executor._execute_via_adapter(
        macro_path=executor._temp_macro_dir / "macro.swp",
        subroutine="Main",
        backing_adapter=SimpleNamespace(),
    )
    assert result["success"] is False
    assert "does not support" in result["error"]


@pytest.mark.asyncio
async def test_execute_via_adapter_handles_attribute_error() -> None:
    """AttributeError in execute_macro should return a failure dict."""
    # Ensure AttributeError is caught and converted to error output.
    executor = VbaMacroExecutor()

    class _Adapter:
        async def execute_macro(self, *_a, **_kw):
            raise AttributeError("bad")

    result = await executor._execute_via_adapter(
        macro_path=executor._temp_macro_dir / "macro.swp",
        subroutine="Main",
        backing_adapter=_Adapter(),
    )
    assert result["success"] is False
    assert "execute_macro failed" in result["error"]
