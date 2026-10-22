"""Settle pause after adapter COM operations (COM pitfall #26).

SolidWorks 2026 SP04 / 3DEXPERIENCE crashed in its idle-time CommandManager
refresh when the API drove it back-to-back. ``_handle_com_operation`` now
pauses after every operation, longer after document open/create/close.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter


@pytest.fixture
def adapter(monkeypatch) -> PyWin32Adapter:
    """A ``PyWin32Adapter`` that thinks it runs on Windows with pywin32."""
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.platform.system", lambda: "Windows"
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
        SimpleNamespace(com_error=RuntimeError),
        raising=False,
    )
    return PyWin32Adapter({})


class TestSettlePause:
    """Pause after COM operations so SolidWorks can finish idle-time UI work."""

    @pytest.fixture
    def sleeps(self, monkeypatch) -> list[float]:
        recorded: list[float] = []
        monkeypatch.setattr(
            "solidworks_mcp.adapters.pywin32_adapter.time.sleep", recorded.append
        )
        monkeypatch.delenv("SOLIDWORKS_MCP_COM_SETTLE_SECONDS", raising=False)
        monkeypatch.delenv("SOLIDWORKS_MCP_DOC_SETTLE_SECONDS", raising=False)
        return recorded

    def test_document_operations_get_the_longer_default(self, adapter, sleeps) -> None:
        adapter._handle_com_operation("create_part", lambda: 1)
        adapter._handle_com_operation("close_model", lambda: 1)
        adapter._handle_com_operation("add_line", lambda: 1)

        assert sleeps == [1.0, 1.0, 0.25]

    def test_pause_runs_after_a_failed_operation(self, adapter, sleeps) -> None:
        def _boom() -> None:
            raise ValueError("bad")

        result = adapter._handle_com_operation("open_model", _boom)

        assert result.is_error
        assert sleeps == [1.0]

    def test_environment_overrides(self, adapter, sleeps, monkeypatch) -> None:
        monkeypatch.setenv("SOLIDWORKS_MCP_COM_SETTLE_SECONDS", "0.5")
        monkeypatch.setenv("SOLIDWORKS_MCP_DOC_SETTLE_SECONDS", "3")

        adapter._handle_com_operation("add_circle", lambda: 1)
        adapter._handle_com_operation("create_assembly", lambda: 1)

        assert sleeps == [0.5, 3.0]

    def test_zero_disables_and_bad_values_fall_back(
        self, adapter, sleeps, monkeypatch
    ) -> None:
        monkeypatch.setenv("SOLIDWORKS_MCP_COM_SETTLE_SECONDS", "0")
        monkeypatch.setenv("SOLIDWORKS_MCP_DOC_SETTLE_SECONDS", "not-a-number")

        adapter._handle_com_operation("add_line", lambda: 1)
        adapter._handle_com_operation("create_part", lambda: 1)

        assert sleeps == [1.0]

    def test_negative_values_clamp_to_zero(self, adapter, sleeps, monkeypatch) -> None:
        monkeypatch.setenv("SOLIDWORKS_MCP_COM_SETTLE_SECONDS", "-2")

        adapter._handle_com_operation("add_line", lambda: 1)

        assert sleeps == []

    def test_execution_time_excludes_the_pause(self, adapter, sleeps) -> None:
        result = adapter._handle_com_operation("create_part", lambda: 1)

        assert result.execution_time < 0.5
