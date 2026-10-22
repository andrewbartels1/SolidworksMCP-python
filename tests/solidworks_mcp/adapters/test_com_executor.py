"""Tests for the ComExecutor STA worker."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

    return SimpleNamespace(
        CoInitialize=_coinitialize, CoUninitialize=_couninitialize
    ), calls


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


def test_com_executor_imports_without_pywin32(import_without) -> None:
    attrs = import_without(
        "solidworks_mcp.adapters.com_executor", ["pythoncom"], ["PYWIN32_AVAILABLE"]
    )

    assert attrs == {"PYWIN32_AVAILABLE": False}


def test_worker_skips_cancelled_work_and_survives_uninit_failure(monkeypatch) -> None:
    """A cancelled item is skipped; a CoUninitialize error never escapes."""
    from concurrent.futures import Future

    from solidworks_mcp.adapters import com_executor

    calls: list[str] = []

    def _uninit_fails() -> None:
        calls.append("uninit")
        raise RuntimeError("apartment already gone")

    fake = SimpleNamespace(
        CoInitialize=lambda: calls.append("init"), CoUninitialize=_uninit_fails
    )
    monkeypatch.setattr(com_executor, "pythoncom", fake, raising=False)
    monkeypatch.setattr(com_executor, "PYWIN32_AVAILABLE", True)

    ex = com_executor.ComExecutor(name="test-cancel")
    ex.start()
    cancelled: Future = Future()
    cancelled.cancel()
    ran: list[str] = []
    ex._queue.put((lambda: ran.append("cancelled"), cancelled))

    assert ex.run(lambda: "after") == "after"
    ex.stop()

    assert ran == []
    assert calls == ["init", "uninit"]


def test_com_executor_start_returns_early_when_thread_alive(monkeypatch):
    """start() should return early when the worker thread is already running. Covers line 104."""
    import threading

    from solidworks_mcp.adapters import com_executor

    executor = com_executor.ComExecutor("test")

    # Create a mock thread that reports as alive
    mock_thread = MagicMock(spec=threading.Thread)
    mock_thread.is_alive = MagicMock(return_value=True)
    executor._thread = mock_thread

    # Should return early without starting a new thread
    executor.start()  # No exception, no new thread started
    mock_thread.start.assert_not_called()


def test_com_executor_start_raises_when_pywin32_unavailable(monkeypatch):
    """start() should raise RuntimeError when PYWIN32_AVAILABLE is False. Covers line 107."""
    from solidworks_mcp.adapters import com_executor

    monkeypatch.setattr(com_executor, "PYWIN32_AVAILABLE", False)

    executor = com_executor.ComExecutor("test")
    with pytest.raises(RuntimeError, match="pywin32"):
        executor.start()


def test_com_executor_start_raises_on_ready_timeout(monkeypatch):
    """start() should raise RuntimeError when worker doesn't signal ready. Covers line 117."""
    import threading

    from solidworks_mcp.adapters import com_executor

    monkeypatch.setattr(com_executor, "PYWIN32_AVAILABLE", True)

    executor = com_executor.ComExecutor("test")

    # Prevent real thread from starting; mock the ready event to never fire
    mock_event = MagicMock()
    mock_event.wait = MagicMock(return_value=False)
    mock_event.clear = MagicMock()
    mock_event.set = MagicMock()
    executor._ready = mock_event

    mock_thread = MagicMock(spec=threading.Thread)
    mock_thread.is_alive = MagicMock(return_value=False)
    mock_thread.start = MagicMock()

    with patch.object(threading, "Thread", return_value=mock_thread):
        with pytest.raises(RuntimeError, match="did not initialize"):
            executor.start(timeout=0.001)


def test_com_executor_stop_warns_when_thread_doesnt_exit(monkeypatch):
    """stop() should warn when thread doesn't exit within timeout. Covers line 138."""
    import threading

    from solidworks_mcp.adapters import com_executor

    executor = com_executor.ComExecutor("test")

    # Simulate a thread that is alive but won't stop
    mock_thread = MagicMock(spec=threading.Thread)
    mock_thread.is_alive = MagicMock(return_value=True)
    mock_thread.join = MagicMock()  # join returns but thread still alive
    executor._thread = mock_thread

    executor.stop(timeout=0.001)
    # Thread should be set to None even though it didn't stop cleanly
    assert executor._thread is None
