"""Tests targeting specific uncovered lines across the codebase.

Each test is annotated with the source file and line numbers it covers.
Lines marked UNREACHABLE are explained in the module docstring at the bottom.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.circuit_breaker import (
    CircuitBreakerAdapter,
    CircuitState,
)
from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

# ---------------------------------------------------------------------------
# circuit_breaker.py: line 205 — _execute_with_circuit_breaker returns when OPEN
# ---------------------------------------------------------------------------


@pytest.fixture
def open_circuit_breaker():
    """Return a CircuitBreakerAdapter already in OPEN state."""
    mock = MockSolidWorksAdapter({})
    cb = CircuitBreakerAdapter(
        adapter=mock,
        failure_threshold=1,
        recovery_timeout=9999.0,
    )
    # Force state to OPEN without timing dependencies
    cb.state = CircuitState.OPEN
    import time

    cb.last_failure_time = time.time()
    return cb


@pytest.mark.asyncio
async def test_execute_with_circuit_breaker_open_returns_error(open_circuit_breaker):
    """_execute_with_circuit_breaker should return an error AdapterResult when OPEN.

    Covers circuit_breaker.py line 205-209.
    """
    result = await open_circuit_breaker.open_model("some/path.sldprt")
    assert result.status == AdapterResultStatus.ERROR
    assert "circuit breaker" in result.error.lower() or "OPEN" in result.error


# ---------------------------------------------------------------------------
# circuit_breaker.py: lines 245-267 — _soc_log when soc_session_id is set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soc_log_writes_record_when_session_set(monkeypatch, tmp_path):
    """_soc_log should call insert_tool_call_record when soc_session_id and input_dict provided.

    Covers circuit_breaker.py lines 245-263.
    """
    records: list[dict] = []
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.insert_tool_call_record",
        lambda **kw: records.append(kw),
    )

    mock = MockSolidWorksAdapter({})
    cb = CircuitBreakerAdapter(adapter=mock, failure_threshold=5)
    cb.soc_session_id = "test-session"

    result_mock = AdapterResult(status=AdapterResultStatus.SUCCESS, data={"ok": True})
    cb._soc_log("test_tool", {"param": "value"}, result_mock, 42.5)

    assert len(records) == 1
    assert records[0]["tool_name"] == "test_tool"
    assert records[0]["success"] is True


@pytest.mark.asyncio
async def test_soc_log_skips_when_no_session_id(monkeypatch):
    """_soc_log should skip when soc_session_id is falsy.

    Covers circuit_breaker.py line 243-244.
    """
    called = []
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.insert_tool_call_record",
        lambda **kw: called.append(kw),
    )

    mock = MockSolidWorksAdapter({})
    cb = CircuitBreakerAdapter(adapter=mock)
    cb.soc_session_id = ""  # falsy

    result_mock = AdapterResult(status=AdapterResultStatus.SUCCESS)
    cb._soc_log("test_tool", {"x": 1}, result_mock, 1.0)
    assert called == []


@pytest.mark.asyncio
async def test_soc_log_handles_insert_exception(monkeypatch):
    """_soc_log should swallow exceptions from insert_tool_call_record.

    Covers circuit_breaker.py lines 264-267.
    """
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.insert_tool_call_record",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("db error")),
    )

    mock = MockSolidWorksAdapter({})
    cb = CircuitBreakerAdapter(adapter=mock)
    cb.soc_session_id = "s1"

    result_mock = AdapterResult(status=AdapterResultStatus.SUCCESS)
    # Should not raise
    cb._soc_log("test_tool", {"x": 1}, result_mock, 1.0)


# ---------------------------------------------------------------------------
# circuit_breaker.py: sketch wrapper methods (lines 728, 738, 757, 779, 800, 810, 823, 843)
# ---------------------------------------------------------------------------


@pytest.fixture
def cb_with_mock():
    """Return (CircuitBreakerAdapter, inner_mock) with a permissive mock adapter."""
    inner = AsyncMock()
    inner.add_spline = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data="spline")
    )
    inner.add_polygon = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data="polygon")
    )
    inner.add_ellipse = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data="ellipse")
    )
    inner.sketch_linear_pattern = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.sketch_circular_pattern = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.sketch_mirror = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.sketch_offset = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.add_sketch_constraint = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )
    inner.is_connected = MagicMock(return_value=False)

    cb = CircuitBreakerAdapter(adapter=inner, failure_threshold=10)
    return cb, inner


@pytest.mark.asyncio
async def test_circuit_breaker_add_spline(cb_with_mock):
    """add_spline should route through _execute_with_circuit_breaker. Covers line 728."""
    cb, inner = cb_with_mock
    result = await cb.add_spline([{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}])
    assert result.is_success
    inner.add_spline.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_add_polygon(cb_with_mock):
    """add_polygon should route through _execute_with_circuit_breaker. Covers line 738."""
    cb, inner = cb_with_mock
    result = await cb.add_polygon(0.0, 0.0, 5.0, 6)
    assert result.is_success
    inner.add_polygon.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_add_ellipse(cb_with_mock):
    """add_ellipse should route through _execute_with_circuit_breaker. Covers line 757."""
    cb, inner = cb_with_mock
    result = await cb.add_ellipse(0.0, 0.0, 3.0, 1.5)
    assert result.is_success
    inner.add_ellipse.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_sketch_linear_pattern(cb_with_mock):
    """sketch_linear_pattern should route through circuit breaker. Covers line 779."""
    cb, inner = cb_with_mock
    result = await cb.sketch_linear_pattern(["e1"], 1.0, 0.0, 5.0, 3)
    assert result.is_success
    inner.sketch_linear_pattern.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_sketch_circular_pattern(cb_with_mock):
    """sketch_circular_pattern should route through circuit breaker. Covers line 800."""
    cb, inner = cb_with_mock
    result = await cb.sketch_circular_pattern(["e1"], 90.0, 4)
    assert result.is_success
    inner.sketch_circular_pattern.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_sketch_mirror(cb_with_mock):
    """sketch_mirror should route through circuit breaker. Covers line 810."""
    cb, inner = cb_with_mock
    result = await cb.sketch_mirror(["e1"], "centerline1")
    assert result.is_success
    inner.sketch_mirror.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_sketch_offset(cb_with_mock):
    """sketch_offset should route through circuit breaker. Covers line 823."""
    cb, inner = cb_with_mock
    result = await cb.sketch_offset(["e1"], 2.5, False)
    assert result.is_success
    inner.sketch_offset.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_add_sketch_constraint(cb_with_mock):
    """add_sketch_constraint should route through circuit breaker. Covers line 843."""
    cb, inner = cb_with_mock
    result = await cb.add_sketch_constraint("e1", "e2", "coincident")
    assert result.is_success
    inner.add_sketch_constraint.assert_awaited_once()


# ---------------------------------------------------------------------------
# circuit_breaker.py: soc_checkpoint (lines 1050-1090)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soc_create_checkpoint_returns_none_when_no_session(monkeypatch):
    """soc_create_checkpoint should return None when soc_session_id is falsy. Covers line 1051."""
    cb = CircuitBreakerAdapter(adapter=MockSolidWorksAdapter({}))
    cb.soc_session_id = ""
    result = await cb.soc_create_checkpoint("my-label", "/tmp/cp.sldprt")
    assert result is None


@pytest.mark.asyncio
async def test_soc_create_checkpoint_creates_record_when_session_set(
    monkeypatch, tmp_path
):
    """soc_create_checkpoint should create a DB record when soc_session_id is set. Covers 1052-1087."""
    snapshots: list[dict] = []
    checkpoints: list[dict] = []

    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.list_tool_call_records",
        lambda *_a, **_kw: [],
    )
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.insert_model_state_snapshot",
        lambda **kw: snapshots.append(kw) or 1,
    )
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.list_model_state_snapshots",
        lambda *_a, **_kw: [{"id": 42}],
    )
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.create_soc_checkpoint",
        lambda **kw: checkpoints.append(kw) or 99,
    )

    cb = CircuitBreakerAdapter(adapter=MockSolidWorksAdapter({}))
    cb.soc_session_id = "test-session"

    result = await cb.soc_create_checkpoint(
        "cp1",
        "/tmp/cp.sldprt",
        feature_tree=[{"name": "Extrude1"}],
    )
    assert result == 99
    assert len(checkpoints) == 1
    assert checkpoints[0]["label"] == "cp1"


@pytest.mark.asyncio
async def test_soc_create_checkpoint_swallows_exceptions(monkeypatch):
    """soc_create_checkpoint exceptions should be caught and return None. Covers lines 1088-1090."""
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.list_tool_call_records",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    cb = CircuitBreakerAdapter(adapter=MockSolidWorksAdapter({}))
    cb.soc_session_id = "test-session"

    result = await cb.soc_create_checkpoint("cp1", "/tmp/cp.sldprt")
    assert result is None


# ---------------------------------------------------------------------------
# com_executor.py: lines 104, 117 — PYWIN32_AVAILABLE guard and timeout
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# vba_adapter.py: lines 153, 172 — create_sweep, create_loft
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vba_adapter_create_sweep_calls_backing(monkeypatch):
    """create_sweep should call _run_with_vba_metadata. Covers vba_adapter.py line 153."""
    from solidworks_mcp.adapters.vba_adapter import VbaGeneratorAdapter

    mock_backing = AsyncMock()
    mock_backing.create_sweep = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )

    adapter = VbaGeneratorAdapter.__new__(VbaGeneratorAdapter)
    adapter._backing_adapter = mock_backing
    adapter._generate_sweep_vba = lambda params: "# sweep vba"

    sweep_params = SimpleNamespace(
        profile_sketch="sketch1",
        path_sketch="path1",
        twist_angle=0.0,
        start_tangent_type="None",
        end_tangent_type="None",
    )

    result = await adapter.create_sweep(sweep_params)
    assert result.is_success
    mock_backing.create_sweep.assert_awaited_once()


@pytest.mark.asyncio
async def test_vba_adapter_create_loft_calls_backing(monkeypatch):
    """create_loft should call _run_with_vba_metadata. Covers vba_adapter.py line 172."""
    from solidworks_mcp.adapters.vba_adapter import VbaGeneratorAdapter

    mock_backing = AsyncMock()
    mock_backing.create_loft = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )

    adapter = VbaGeneratorAdapter.__new__(VbaGeneratorAdapter)
    adapter._backing_adapter = mock_backing
    adapter._generate_loft_vba = lambda params: "# loft vba"

    loft_params = SimpleNamespace(
        profile_sketches=["s1", "s2"],
        guide_curves=[],
        start_tangent_type="None",
        end_tangent_type="None",
    )

    result = await adapter.create_loft(loft_params)
    assert result.is_success
    mock_backing.create_loft.assert_awaited_once()


# ---------------------------------------------------------------------------
# soc_rewind.py: line 176 — return None when script_text is None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rewind_to_checkpoint_returns_none_when_no_script(monkeypatch):
    """rewind_to_checkpoint should return None when script_text is not provided. Covers line 176."""
    from solidworks_mcp.agents.soc_rewind import rewind_to_checkpoint

    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.get_soc_checkpoint",
        lambda *_a, **_kw: {"file_path": "/tmp/cp.sldprt"},
    )

    class _Adapter:
        async def open_model(self, _path):
            return SimpleNamespace(is_success=True, error="")

    result = await rewind_to_checkpoint(
        _Adapter(), session_id="s1", label="cp1", script_text=None
    )
    assert result is None


# ---------------------------------------------------------------------------
# docs_service.py: lines 183-184 — idx.save() after ingest
# ---------------------------------------------------------------------------


def test_docs_service_ingest_saves_index(monkeypatch, tmp_path):
    """ingest_reference_source should call idx.save() after ingesting. Covers lines 183-184."""
    from solidworks_mcp.ui.services import docs_service

    save_calls: list = []
    ingest_calls: list = []

    class _FakeIndex:
        def ingest_text(self, text, source=None, tags=None):
            ingest_calls.append({"text": text, "source": source})

        def save(self):
            save_calls.append(True)

        @classmethod
        def load(cls, namespace=None, rag_dir=None):
            return cls()

    # Patch the inline import by setting it on the vector_rag module
    from solidworks_mcp.agents import vector_rag

    monkeypatch.setattr(vector_rag, "VectorRAGIndex", _FakeIndex)

    monkeypatch.setattr(
        docs_service,
        "ensure_dashboard_session"
        if hasattr(docs_service, "ensure_dashboard_session")
        else "__missing__",
        lambda *_a, **_kw: None,
        raising=False,
    )

    # Create a real markdown file to ingest
    md_file = tmp_path / "test.md"
    md_file.write_text("# Test\nHello world content for RAG.", encoding="utf-8")

    # Patch ensure_dashboard_session and build_dashboard_state
    monkeypatch.setattr(
        "solidworks_mcp.ui.services.session_service.ensure_dashboard_session",
        lambda *_a, **_kw: None,
    )
    monkeypatch.setattr(
        "solidworks_mcp.ui.services.session_service.build_dashboard_state",
        lambda *_a, **_kw: {"ok": True},
    )
    monkeypatch.setattr(docs_service, "DEFAULT_RAG_DIR", tmp_path)
    # Avoid DB writes from insert_tool_call_record
    monkeypatch.setattr(docs_service, "insert_tool_call_record", lambda **_kw: None)

    docs_service.ingest_reference_source(
        "s1",
        source_path=str(md_file),
        namespace="test-ns",
    )

    assert len(save_calls) == 1
    assert len(ingest_calls) >= 1


# ---------------------------------------------------------------------------
# service.py: lines 189, 413, 458 — RecoverableFailure from hasattr-matching object
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_structured_agent_wraps_rf_like_object(monkeypatch):
    """_run_structured_agent should wrap objects with RF-like attributes. Covers service.py line 189."""
    from solidworks_mcp.ui import service

    class RFLike:
        explanation = "Something went wrong in the operation"
        remediation_steps = ["fix it by retrying"]
        retry_focus = "do better next time"
        should_retry = True

    monkeypatch.setattr(
        service,
        "_ORIG_RUN_STRUCTURED_AGENT",
        AsyncMock(return_value=RFLike()),
    )

    result = await service._run_structured_agent(system_prompt="x", user_prompt="y")
    # Should be wrapped as a RecoverableFailure
    assert hasattr(result, "explanation")
    assert "Something went wrong" in result.explanation


# ---------------------------------------------------------------------------
# service.py: line 199 — ensure_uploaded_model_dir
# ---------------------------------------------------------------------------


def test_ensure_uploaded_model_dir_returns_path(tmp_path):
    """ensure_uploaded_model_dir should return a valid directory. Covers service.py line 199."""
    from solidworks_mcp.ui import service

    result = service.ensure_uploaded_model_dir(tmp_path)
    assert result.exists()


# ---------------------------------------------------------------------------
# server.py: line 180 — return early when no md files
# ---------------------------------------------------------------------------


def test_startup_ingest_returns_early_when_no_md_files(monkeypatch, tmp_path):
    """_startup_ingest_design_knowledge should return early when directory has no md files. Covers line 180."""
    from solidworks_mcp.ui import server

    empty_dir = tmp_path / "design_knowledge"
    empty_dir.mkdir()

    mock_dir = MagicMock()
    mock_dir.is_dir = MagicMock(return_value=True)
    mock_dir.glob = MagicMock(return_value=[])  # No .md files → line 180

    with patch.object(server, "FilePath") as mock_fpath:
        mock_instance = MagicMock()
        mock_instance.parent.parent.__truediv__ = MagicMock(return_value=mock_dir)
        mock_fpath.return_value = mock_instance
        server._startup_ingest_design_knowledge()
    # No assertion needed — success = no exception raised


# ---------------------------------------------------------------------------
# local_llm.py: lines 348-349, 379-380 — platform-specific RAM detection
# ---------------------------------------------------------------------------


def test_detect_gpu_vram_wmic_path(monkeypatch):
    """_detect_gpu_vram_gb should use wmic on Windows when nvidia-smi fails. Covers lines 348-349."""
    import subprocess

    from solidworks_mcp.ui import local_llm

    # Simulate Windows and nvidia-smi failure, then wmic success
    monkeypatch.setattr(local_llm.platform, "system", lambda: "Windows")

    def _mock_check_output(cmd, *args, **kwargs):
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        if "nvidia-smi" in cmd_str:
            raise subprocess.CalledProcessError(1, "nvidia-smi")
        if "wmic" in cmd_str and "VideoController" in cmd_str:
            return "AdapterRAM\r\n4294967296\r\n"  # 4 GB in bytes
        raise RuntimeError(f"unexpected cmd: {cmd_str}")

    monkeypatch.setattr(local_llm.subprocess, "check_output", _mock_check_output)

    result = local_llm._detect_gpu_vram_gb()
    assert result == pytest.approx(4.0, abs=0.1)


def test_detect_system_ram_gb_psutil_path(monkeypatch):
    """_detect_system_ram_gb should return RAM via psutil when available. Covers lines 363."""
    from solidworks_mcp.ui import local_llm

    # Inject a fake psutil module
    fake_psutil = MagicMock()
    fake_psutil.virtual_memory.return_value = SimpleNamespace(total=8 * 1024**3)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    result = local_llm._detect_system_ram_gb()
    assert result == pytest.approx(8.0, abs=0.1)


def test_detect_system_ram_gb_wmic_path(monkeypatch):
    """_detect_system_ram_gb should fall back to wmic on Windows. Covers lines 379-380."""
    from solidworks_mcp.ui import local_llm

    # Remove psutil so the ImportError path runs
    monkeypatch.setitem(sys.modules, "psutil", None)
    monkeypatch.setattr(local_llm.platform, "system", lambda: "Windows")

    def _mock_check_output(cmd, *args, **kwargs):
        return "TotalPhysicalMemory\r\n8589934592\r\n"  # 8 GB

    monkeypatch.setattr(local_llm.subprocess, "check_output", _mock_check_output)

    result = local_llm._detect_system_ram_gb()
    assert result == pytest.approx(8.0, abs=0.1)


# ---------------------------------------------------------------------------
# history_db.py: lines 865-882 — update_plan_checkpoint
# ---------------------------------------------------------------------------


def test_update_plan_checkpoint_existing(tmp_path):
    """update_plan_checkpoint should update an existing checkpoint. Covers lines 865-882."""
    from solidworks_mcp.agents.history_db import (
        init_db,
        insert_plan_checkpoint,
        list_plan_checkpoints,
        update_plan_checkpoint,
    )

    db_path = tmp_path / "test.db"
    init_db(db_path=db_path)
    insert_plan_checkpoint(
        session_id="s1",
        title="Test Checkpoint",
        planned_action_json='{"part_name": "test"}',
        checkpoint_index=0,
        db_path=db_path,
    )

    rows = list_plan_checkpoints("s1", db_path=db_path)
    assert len(rows) == 1
    cp_id = rows[0]["id"]

    update_plan_checkpoint(
        cp_id, executed=True, result_json='{"ok": true}', db_path=db_path
    )

    rows_after = list_plan_checkpoints("s1", db_path=db_path)
    assert rows_after[0]["executed"] is True


def test_update_plan_checkpoint_missing(tmp_path):
    """update_plan_checkpoint should return None for a missing checkpoint id."""
    from solidworks_mcp.agents.history_db import init_db, update_plan_checkpoint

    db_path = tmp_path / "test.db"
    init_db(db_path=db_path)
    result = update_plan_checkpoint(99999, executed=True, db_path=db_path)
    assert result is None


# ---------------------------------------------------------------------------
# history_db.py: lines 865-882 — update_plan_checkpoint_planned_action
# ---------------------------------------------------------------------------


def test_update_plan_checkpoint_planned_action(tmp_path):
    """update_plan_checkpoint_planned_action should update planned_action_json. Covers 865-882."""
    from solidworks_mcp.agents.history_db import (
        init_db,
        insert_plan_checkpoint,
        list_plan_checkpoints,
        update_plan_checkpoint_planned_action,
    )

    db_path = tmp_path / "test.db"
    init_db(db_path=db_path)
    insert_plan_checkpoint(
        session_id="s1",
        title="Test",
        planned_action_json='{"part_name": "old"}',
        checkpoint_index=0,
        db_path=db_path,
    )
    rows = list_plan_checkpoints("s1", db_path=db_path)
    cp_id = rows[0]["id"]

    update_plan_checkpoint_planned_action(
        cp_id, planned_action_json='{"part_name": "new"}', db_path=db_path
    )
    rows_after = list_plan_checkpoints("s1", db_path=db_path)
    assert rows_after[0]["planned_action_json"] == '{"part_name": "new"}'


def test_update_plan_checkpoint_planned_action_missing(tmp_path):
    """update_plan_checkpoint_planned_action should return None when row missing. Covers line 872."""
    from solidworks_mcp.agents.history_db import (
        init_db,
        update_plan_checkpoint_planned_action,
    )

    db_path = tmp_path / "test.db"
    init_db(db_path=db_path)
    # Non-existent ID → row is None → early return
    result = update_plan_checkpoint_planned_action(
        99999, planned_action_json="{}", db_path=db_path
    )
    assert result is None


# ---------------------------------------------------------------------------
# history_db.py: lines 1290-1305 — create_soc_checkpoint
# ---------------------------------------------------------------------------


def test_create_soc_checkpoint_inserts_and_returns_id(tmp_path):
    """create_soc_checkpoint should persist a checkpoint and return its id. Covers 1290-1305."""
    from solidworks_mcp.agents.history_db import (
        create_soc_checkpoint,
        get_soc_checkpoint,
        init_db,
    )

    db_path = tmp_path / "test.db"
    init_db(db_path=db_path)

    cp_id = create_soc_checkpoint(
        session_id="s1",
        label="base-extrude",
        file_path="/tmp/cp.sldprt",
        db_path=db_path,
    )
    assert isinstance(cp_id, int)
    assert cp_id > 0

    row = get_soc_checkpoint("s1", "base-extrude", db_path=db_path)
    assert row is not None
    assert row["file_path"] == "/tmp/cp.sldprt"


# ---------------------------------------------------------------------------
# history_db.py: lines 1359-1370 — get_soc_checkpoint returns None for missing
# ---------------------------------------------------------------------------


def test_get_soc_checkpoint_returns_none_for_missing(tmp_path):
    """get_soc_checkpoint should return None when label doesn't exist. Covers lines 1359-1370."""
    from solidworks_mcp.agents.history_db import get_soc_checkpoint, init_db

    db_path = tmp_path / "test.db"
    init_db(db_path=db_path)

    result = get_soc_checkpoint("s1", "nonexistent-label", db_path=db_path)
    assert result is None


# ---------------------------------------------------------------------------
# vector_rag.py: lines 132-135 — _AwaitableQueryResult.__await__
# ---------------------------------------------------------------------------


def test_awaitable_query_result_creation():
    """_AwaitableQueryResult should be a str subclass with _hits. Covers lines 126-129."""
    from solidworks_mcp.agents.vector_rag import _AwaitableQueryResult

    hits = [{"text": "hello", "score": 0.9}]
    result = _AwaitableQueryResult("found text", hits=hits)
    assert result == "found text"
    assert result._hits == hits


@pytest.mark.asyncio
async def test_awaitable_query_result_await():
    """_AwaitableQueryResult.__await__ should return hits list. Covers lines 132-135."""
    from solidworks_mcp.agents.vector_rag import _AwaitableQueryResult

    hits = [{"text": "some result", "score": 0.8}]
    result = _AwaitableQueryResult("text", hits=hits)
    awaited = await result
    assert isinstance(awaited, list)
    assert awaited == hits


# ---------------------------------------------------------------------------
# vector_rag.py: lines 246-249 — VectorRAGIndex.__await__
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vector_rag_index_await():
    """VectorRAGIndex.__await__ should return self. Covers lines 246-249."""
    from solidworks_mcp.agents.vector_rag import VectorRAGIndex

    idx = VectorRAGIndex(namespace="test")
    awaited = await idx
    assert awaited is idx


# ---------------------------------------------------------------------------
# vector_rag.py: line 565 — build_solidworks_api_docs_index returns early when no path
# ---------------------------------------------------------------------------


def test_build_solidworks_api_docs_index_returns_empty_when_no_path():
    """build_solidworks_api_docs_index should return early when docs_json_path is None. Covers line 565."""
    from solidworks_mcp.agents.vector_rag import (
        VectorRAGIndex,
        build_solidworks_api_docs_index,
    )

    result = build_solidworks_api_docs_index(docs_json_path=None)
    assert isinstance(result, VectorRAGIndex)
    assert result.chunk_count == 0


# ---------------------------------------------------------------------------
# soc_rewind.py: line 37 — TYPE_CHECKING pass block
# UNREACHABLE: see note at bottom of file
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Unreachability Report
# ---------------------------------------------------------------------------
#
# parameter_repair_service.py lines 266-267:
#   The `elif missing_key == "sketch_name" and "last_sketch_name" in context:` branch
#   is dead code. Examining TOOL_PARAM_SCHEMAS, `sketch_name` only appears as
#   *optional* (never *required*) in any registered tool. The auto-repair loop only
#   iterates over `validation.missing_keys` (required keys that are absent), so
#   `sketch_name` is NEVER in `missing_keys`. This branch cannot fire without adding
#   a tool that lists `sketch_name` as required. Candidate fix: promote `sketch_name`
#   to required in a future tool, or remove the dead branch.
#
# soc_rewind.py line 37 (`pass` inside `if TYPE_CHECKING:`):
#   The `if TYPE_CHECKING:` block is guarded by `typing.TYPE_CHECKING`, which is
#   always `False` at runtime (it's True only in static analysis tools like mypy).
#   The `pass` at line 37 is therefore unreachable at test-time. This is intentional
#   Python idiom for imports used only in type annotations. No test can cover it.
#   Candidate fix: remove the empty `if TYPE_CHECKING: pass` block, since it serves
#   no purpose.
#
# com_executor.py line 48 (`PYWIN32_AVAILABLE = True`):
#   This line is covered on Windows (where pywin32 is installed) but missed in CI
#   (Linux, no pywin32). Conversely, line 50 (`PYWIN32_AVAILABLE = False`) is covered
#   in CI but missed locally. Both can be tested simultaneously by patching sys.modules
#   to force an ImportError, but running the test locally would then also cover line 50
#   while line 48 remains uncovered in CI. The two lines represent mutually exclusive
#   import paths (pywin32 available vs. not) that cannot both be covered in a single
#   environment. Candidate fix: accept the partial coverage or use a conditional
#   `# pragma: no cover` marker.
#
# com_executor.py lines 239-240 (CoUninitialize in worker finally):
#   The `except Exception: pass` around `pythoncom.CoUninitialize()` inside the
#   worker thread's `finally` block is only reachable if `CoUninitialize` raises an
#   exception. pywin32's CoUninitialize is a thin COM wrapper that essentially never
#   raises (it's a void COM call). Even if it did raise, reaching the finally block
#   requires the ComExecutor's worker thread to be running, which itself requires
#   pywin32 on Windows. Candidate fix: accept this as platform-only code with
#   `# pragma: no cover`, or restructure to always hit the branch in a
#   controlled way.
