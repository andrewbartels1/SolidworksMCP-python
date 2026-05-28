"""Tests for the ComExecutor STA worker."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest


def _fake_pythoncom(*, fail_init: bool = False, calls: list[str] | None = None):
    """Create a fake pythoncom module for ComExecutor tests."""
    calls = calls if calls is not None else []

    def _coinitialize():
        calls.append("init")
        if fail_init:
            raise RuntimeError("init failed")

    def _couninitialize():
        calls.append("uninit")

    return SimpleNamespace(CoInitialize=_coinitialize, CoUninitialize=_couninitialize), calls


def test_start_raises_when_pywin32_missing(monkeypatch) -> None:
    """Start should raise when pywin32 is unavailable."""
    from solidworks_mcp.adapters import com_executor

    # Ensure the guard path is exercised for missing pywin32.
    monkeypatch.setattr(com_executor, "PYWIN32_AVAILABLE", False)
    executor = com_executor.ComExecutor(name="test-missing")
    with pytest.raises(RuntimeError, match="pywin32"):
        executor.start()


def test_submit_requires_running_executor() -> None:
    """Submit should fail when the executor has not been started."""
    from solidworks_mcp.adapters.com_executor import ComExecutor

    # Verify the pre-start guard on submit().
    executor = ComExecutor(name="test-submit")
    with pytest.raises(RuntimeError, match="not running"):
        executor.submit(lambda: "nope")


def test_run_executes_on_worker_and_cleans_up(monkeypatch) -> None:
    """Run should execute on the worker thread and CoUninitialize on stop."""
    from solidworks_mcp.adapters import com_executor

    fake_pythoncom, calls = _fake_pythoncom()
    monkeypatch.setattr(com_executor, "pythoncom", fake_pythoncom, raising=False)
    monkeypatch.setattr(com_executor, "PYWIN32_AVAILABLE", True)

    # Start the worker and confirm work executes off the caller thread.
    executor = com_executor.ComExecutor(name="test-worker")
    executor.start()
    worker_name = executor.run(lambda: threading.current_thread().name)
    assert worker_name != threading.current_thread().name
    executor.stop()

    assert "init" in calls
    assert "uninit" in calls


def test_run_propagates_exceptions(monkeypatch) -> None:
    """Exceptions inside callables should propagate to the caller."""
    from solidworks_mcp.adapters import com_executor

    fake_pythoncom, _calls = _fake_pythoncom()
    monkeypatch.setattr(com_executor, "pythoncom", fake_pythoncom, raising=False)
    monkeypatch.setattr(com_executor, "PYWIN32_AVAILABLE", True)

    # The raised exception should surface through run().
    with com_executor.ComExecutor(name="test-exc") as executor:
        with pytest.raises(ZeroDivisionError):
            executor.run(lambda: 1 / 0)


def test_start_unblocks_when_coinitialize_fails(monkeypatch) -> None:
    """Start should return even if CoInitialize fails inside the worker."""
    from solidworks_mcp.adapters import com_executor

    fake_pythoncom, _calls = _fake_pythoncom(fail_init=True)
    monkeypatch.setattr(com_executor, "pythoncom", fake_pythoncom, raising=False)
    monkeypatch.setattr(com_executor, "PYWIN32_AVAILABLE", True)

    # Worker should signal readiness then exit; submit should fail fast.
    executor = com_executor.ComExecutor(name="test-init-fail")
    executor.start()
    assert executor._thread is not None
    assert not executor._thread.is_alive()
    with pytest.raises(RuntimeError, match="not running"):
        executor.submit(lambda: "nope")
    executor.stop()
