"""Tests for the checkpoint execution service helpers."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.ui.services import checkpoint_service as service


def _ok_result() -> SimpleNamespace:
    """Return a success-shaped adapter result."""
    return SimpleNamespace(is_success=True, error="")


class StubAdapter:
    """Minimal adapter stub that records calls."""

    def __init__(self, *, fail_connect: bool = False) -> None:
        self.calls: list[object] = []
        self.fail_connect = fail_connect

    async def connect(self) -> None:
        """Record connect calls (optionally fail)."""
        self.calls.append("connect")
        if self.fail_connect:
            raise RuntimeError("connect failed")

    async def disconnect(self) -> None:
        """Record disconnect calls."""
        self.calls.append("disconnect")

    async def create_part(self, name: str) -> SimpleNamespace:
        """Record create_part calls."""
        self.calls.append(("create_part", name))
        return _ok_result()

    async def create_assembly(self, name: str) -> SimpleNamespace:
        """Record create_assembly calls."""
        self.calls.append(("create_assembly", name))
        return _ok_result()

    async def open_model(self, path: str) -> SimpleNamespace:
        """Record open_model calls."""
        self.calls.append(("open_model", path))
        return _ok_result()

    async def create_sketch(self, plane: str) -> SimpleNamespace:
        """Record create_sketch calls."""
        self.calls.append(("create_sketch", plane))
        return _ok_result()

    async def exit_sketch(self) -> SimpleNamespace:
        """Record exit_sketch calls."""
        self.calls.append("exit_sketch")
        return _ok_result()

    async def add_line(self, x1, y1, x2, y2) -> SimpleNamespace:
        """Record add_line calls."""
        self.calls.append(("add_line", x1, y1, x2, y2))
        return _ok_result()

    async def add_rectangle(self, x, y, w, h) -> SimpleNamespace:
        """Record add_rectangle calls."""
        self.calls.append(("add_rectangle", x, y, w, h))
        return _ok_result()

    async def add_circle(self, cx, cy, r) -> SimpleNamespace:
        """Record add_circle calls."""
        self.calls.append(("add_circle", cx, cy, r))
        return _ok_result()

    async def add_centerline(self, x1, y1, x2, y2) -> SimpleNamespace:
        """Record add_centerline calls."""
        self.calls.append(("add_centerline", x1, y1, x2, y2))
        return _ok_result()

    async def add_arc(self, cx, cy, sx, sy, ex, ey) -> SimpleNamespace:
        """Record add_arc calls."""
        self.calls.append(("add_arc", cx, cy, sx, sy, ex, ey))
        return _ok_result()

    async def create_extrusion(self, params) -> SimpleNamespace:
        """Record create_extrusion calls."""
        self.calls.append(("create_extrusion", params.depth))
        return _ok_result()

    async def create_cut_extrude(self, params) -> SimpleNamespace:
        """Record create_cut_extrude calls."""
        self.calls.append(("create_cut_extrude", params.depth))
        return _ok_result()

    async def create_cut(self, sketch_name: str, depth: float) -> SimpleNamespace:
        """Record create_cut calls."""
        self.calls.append(("create_cut", sketch_name, depth))
        return _ok_result()

    async def add_fillet(self, radius: float, edge_names: list[str]) -> SimpleNamespace:
        """Record add_fillet calls."""
        self.calls.append(("add_fillet", radius, edge_names))
        return _ok_result()

    async def check_sketch_fully_defined(self, sketch_name) -> SimpleNamespace:
        """Record check_sketch_fully_defined calls."""
        self.calls.append(("check_sketch_fully_defined", sketch_name))
        return _ok_result()

    async def save_file(self, file_path: str) -> SimpleNamespace:
        """Record save_file calls."""
        self.calls.append(("save_file", file_path))
        return _ok_result()

    async def get_model_info(self) -> SimpleNamespace:
        """Record get_model_info calls."""
        self.calls.append("get_model_info")
        return _ok_result()

    async def list_features(self, include_suppressed: bool = True) -> SimpleNamespace:
        """Record list_features calls."""
        self.calls.append(("list_features", include_suppressed))
        return _ok_result()

    async def get_mass_properties(self) -> SimpleNamespace:
        """Record get_mass_properties calls."""
        self.calls.append("get_mass_properties")
        return _ok_result()

    async def export_image(self, payload: dict[str, object]) -> SimpleNamespace:
        """Record export_image calls."""
        self.calls.append(("export_image", payload))
        return _ok_result()

    async def check_interference(self, payload: dict[str, object]) -> SimpleNamespace:
        """Record check_interference calls."""
        self.calls.append(("check_interference", payload))
        return _ok_result()


def test_planned_tools_and_payload_ordering() -> None:
    """Planned tool payloads should be ordered predictably."""
    # Validate list coercion and suffix ordering logic.
    planned = {
        "tools": [1, "create_part"],
        "create_part": {"part_name": "base"},
        "create_part#2": {"part_name": "second"},
        "create_part#10": {"part_name": "tenth"},
        "create_part#alpha": {"part_name": "alpha"},
    }
    assert service._planned_tools(planned) == ["1", "create_part"]
    payloads = service._planned_tool_payloads(planned, "create_part")
    assert [p["part_name"] for p in payloads] == ["base", "second", "tenth", "alpha"]


def test_pf_pv_helpers_use_defaults() -> None:
    """Float/list helpers should fall back to defaults when needed."""
    # Cover conversion and default behavior for helper utilities.
    planned = {"depth": "3.5", "rect": [1, 2, 3, 4], "bad": ["x", "y"]}
    assert service._pf(planned, "depth", default=1.0) == 3.5
    assert service._pf(planned, "missing", default=2.0) == 2.0
    assert service._pv(planned, "rect", size=4) == [1.0, 2.0, 3.0, 4.0]
    assert service._pv(planned, "bad", size=2, default=[9.0, 9.0]) == [9.0, 9.0]


@pytest.mark.asyncio
async def test_execute_tool_create_and_sketch_branches() -> None:
    """Create/open/sketch branches should return success runs."""
    # Exercise create/open/sketch/exit branches in execute_tool.
    adapter = StubAdapter()

    result = await service._execute_tool(adapter, {"part_name": "demo"}, "create_part")
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {"assembly_name": "asm"}, "create_assembly")
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {"model_path": "C:/tmp/part.sldprt"}, "open_model")
    assert result["status"] == "success"

    result = await service._execute_tool(
        adapter,
        {"create_sketch": {"sketch_plane": "Right"}},
        "create_sketch",
    )
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {}, "exit_sketch")
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_execute_tool_geometry_branches() -> None:
    """Geometry helpers should convert vectors and call adapter methods."""
    # Exercise line/rectangle/circle/centerline/arc branches.
    adapter = StubAdapter()

    result = await service._execute_tool(adapter, {"line_mm": [0, 0, 10, 10]}, "add_line")
    assert result["status"] == "success"

    result = await service._execute_tool(
        adapter,
        {"line_start_mm": [0, 0], "line_end_mm": [5, 5]},
        "add_line",
    )
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {"rectangle_mm": [0, 0, 5, 2]}, "add_rectangle")
    assert result["status"] == "success"

    result = await service._execute_tool(
        adapter,
        {"circle_center_mm": [1, 2], "circle_radius_mm": 3},
        "add_circle",
    )
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {"centerline_mm": [0, 0, 0, 10]}, "add_centerline")
    assert result["status"] == "success"

    result = await service._execute_tool(
        adapter,
        {"arc_center_mm": [0, 0], "arc_start_mm": [1, 0], "arc_end_mm": [0, 1]},
        "add_arc",
    )
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_execute_tool_feature_branches() -> None:
    """Feature branches should accept depth and sketch info."""
    # Exercise extrusion/cut/fillet/definition branches.
    adapter = StubAdapter()

    result = await service._execute_tool(adapter, {"depth_mm": 5}, "create_extrusion")
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {"depth": 4}, "create_cut_extrude")
    assert result["status"] == "success"

    result = await service._execute_tool(
        adapter,
        {"depth": 3, "sketch_name": "Sketch1"},
        "create_cut",
    )
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {"depth": 2}, "create_cut")
    assert result["status"] == "success"

    result = await service._execute_tool(
        adapter,
        {"radius_mm": 1.5, "edge_names": ["Edge1"]},
        "add_fillet",
    )
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {"sketch_name": "Sketch1"}, "check_sketch_fully_defined")
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_execute_tool_info_branches() -> None:
    """Info and export branches should return success runs."""
    # Exercise save/get/list/analyze/export branches.
    adapter = StubAdapter()

    result = await service._execute_tool(adapter, {"file_path": "C:/tmp/test.sldprt"}, "save_file")
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {}, "get_model_info")
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {}, "list_features")
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {}, "get_mass_properties")
    assert result["status"] == "success"

    result = await service._execute_tool(adapter, {}, "analyze_geometry")
    assert result["status"] == "success"

    result = await service._execute_tool(
        adapter,
        {"export_image": {"file_path": "C:/tmp/test.png", "format_type": "png"}},
        "export_image",
    )
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_execute_tool_missing_paths_raise() -> None:
    """Missing paths should raise validation errors."""
    # Ensure open_model/save_file validate required inputs.
    adapter = StubAdapter()
    with pytest.raises(ValueError, match="model_path"):
        await service._execute_tool(adapter, {}, "open_model")
    with pytest.raises(ValueError, match="file_path"):
        await service._execute_tool(adapter, {}, "save_file")


@pytest.mark.asyncio
async def test_execute_tool_export_requires_object_payload() -> None:
    """export_image should reject non-dict payloads."""
    # Ensure export_image validation rejects invalid payload shapes.
    adapter = StubAdapter()
    with pytest.raises(ValueError, match="export_image must be an object"):
        await service._execute_tool(adapter, {"export_image": "bad"}, "export_image")


@pytest.mark.asyncio
async def test_run_checkpoint_tools_handles_mocked_and_unknown(tmp_path, monkeypatch) -> None:
    """Mocked or unknown tools should be recorded without failures."""
    # Exercise the mocked tool and unknown tool paths in _run_checkpoint_tools.
    adapter = StubAdapter()

    async def _create_adapter(_cfg):
        return adapter

    monkeypatch.setattr(service, "create_adapter", _create_adapter)
    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "_checkpoint_script_dir", lambda _sid: tmp_path)

    planned = {"tools": ["check_interference", "unknown_tool"]}
    summary = await service._run_checkpoint_tools(planned, session_id="s1", checkpoint_index=1)

    assert summary["failed_tools"] == []
    assert set(summary["mocked_tools"]) == {"check_interference", "unknown_tool"}
    assert Path(summary["script_path"]).exists()


@pytest.mark.asyncio
async def test_run_checkpoint_tools_handles_connect_failure(tmp_path, monkeypatch) -> None:
    """Connection failures should surface as checkpoint.execute errors."""
    # Validate the adapter connection failure path.
    adapter = StubAdapter(fail_connect=True)

    async def _create_adapter(_cfg):
        return adapter

    monkeypatch.setattr(service, "create_adapter", _create_adapter)
    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "_checkpoint_script_dir", lambda _sid: tmp_path)

    planned = {"tools": ["create_part"], "part_name": "demo"}
    summary = await service._run_checkpoint_tools(planned, session_id="s1", checkpoint_index=2)

    assert summary["failed_tools"] == ["checkpoint.execute"]
    assert summary["tool_runs"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_run_checkpoint_tools_disconnect_raises(tmp_path, monkeypatch) -> None:
    """Disconnect exceptions in run_checkpoint_tools should be swallowed."""
    # Exercise the except-in-finally at lines 963-964.

    class DisconnectRaisesAdapter(StubAdapter):
        async def disconnect(self):
            raise RuntimeError("disconnect failed")

    adapter = DisconnectRaisesAdapter()

    async def _create_adapter(_cfg):
        return adapter

    monkeypatch.setattr(service, "create_adapter", _create_adapter)
    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "_checkpoint_script_dir", lambda _sid: tmp_path)

    planned = {"tools": ["unknown_tool"]}
    summary = await service._run_checkpoint_tools(planned, session_id="s1", checkpoint_index=1)

    # Disconnect raising should not prevent the summary from being returned.
    assert "tool_runs" in summary
    assert summary["failed_tools"] == []


@pytest.mark.asyncio
async def test_open_empty_part_before_checkpoint_handles_preview_error(monkeypatch, tmp_path) -> None:
    """Preview failures should be captured in metadata updates."""
    # Exercise the preview-refresh exception path in the helper.
    adapter = StubAdapter()
    merge_calls: list[dict[str, object]] = []

    async def _create_adapter(_cfg):
        return adapter

    async def _refresh_preview(*_a, **_kw):
        raise RuntimeError("boom")

    from solidworks_mcp.ui.services import preview_service

    monkeypatch.setattr(service, "create_adapter", _create_adapter)
    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))
    monkeypatch.setattr(service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(service, "ensure_preview_dir", lambda: tmp_path)
    monkeypatch.setattr(preview_service, "refresh_preview", _refresh_preview)

    result = await service._open_empty_part_before_checkpoint(
        session_id="s1",
        session_row={"user_goal": "demo"},
        db_path=None,
        api_origin="http://localhost",
    )

    assert result["status"] == "success"
    assert any("preview refresh is still pending" in call.get("preview_status", "") for call in merge_calls)


@pytest.mark.asyncio
async def test_execute_next_checkpoint_opens_empty_and_records_failure(monkeypatch) -> None:
    """execute_next_checkpoint should open empty parts and record failures."""
    # Validate the empty-part pre-step and failed_tools message branch.
    session_row = {
        "user_goal": "demo",
        "source_mode": "plan",
        "accepted_family": None,
        "metadata_json": json.dumps(
            {
                "workflow_mode": "new_design",
                "active_model_path": "",
                "new_design_part_opened": False,
            }
        ),
    }
    checkpoints = [
        {
            "id": 1,
            "checkpoint_index": 0,
            "title": "First",
            "executed": False,
            # Use create_sketch (not create_part/assembly/open_model) so that
            # _should_open_empty_part returns True and the open-empty step fires.
            "planned_action_json": json.dumps({"tools": ["create_sketch"]}),
        }
    ]
    open_calls: list[str] = []
    merge_calls: list[dict[str, object]] = []

    from solidworks_mcp.ui.services import session_service

    monkeypatch.setattr(session_service, "ensure_dashboard_session", lambda *_a, **_kw: session_row)
    monkeypatch.setattr(service, "list_plan_checkpoints", lambda *_a, **_kw: checkpoints)
    async def _open_empty(**_kw):
        open_calls.append("open")

    async def _run_checkpoint(*_a, **_kw):
        return {
            "failed_tools": ["create_sketch"],
            "tool_runs": [{"tool": "create_sketch", "status": "error", "message": "fail"}],
            "script_path": "script.py",
            "script_text": "",
            "stdout_text": "",
            "stderr_text": "",
            "validation_failures": [],
        }

    monkeypatch.setattr(service, "_open_empty_part_before_checkpoint", _open_empty)
    monkeypatch.setattr(service, "_run_checkpoint_tools", _run_checkpoint)
    monkeypatch.setattr(service, "update_plan_checkpoint", lambda *_a, **_kw: None)
    monkeypatch.setattr(service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(service, "upsert_design_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})

    result = await service.execute_next_checkpoint("s1")

    assert result == {"ok": True}
    assert open_calls == ["open"]
    assert any("failed" in call.get("latest_error_text", "") for call in merge_calls)


@pytest.mark.asyncio
async def test_execute_next_checkpoint_all_executed(monkeypatch) -> None:
    """execute_next_checkpoint should short-circuit when all checkpoints are done."""
    # Provide a list of already-executed checkpoints and assert early return.
    merge_calls: list[dict[str, object]] = []

    from solidworks_mcp.ui.services import session_service

    monkeypatch.setattr(
        session_service,
        "ensure_dashboard_session",
        lambda *_a, **_kw: {"user_goal": "demo", "source_mode": "plan", "metadata_json": "{}"},
    )
    monkeypatch.setattr(
        service, "list_plan_checkpoints",
        lambda *_a, **_kw: [{"executed": True, "id": 1, "checkpoint_index": 0, "title": "Done",
                              "planned_action_json": "{}"}],
    )
    monkeypatch.setattr(service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})

    result = await service.execute_next_checkpoint("s1")

    assert result == {"ok": True}
    assert any("All checkpoints" in call.get("latest_message", "") for call in merge_calls)


@pytest.mark.asyncio
async def test_execute_next_checkpoint_mocked_only_message(monkeypatch) -> None:
    """Mocked-only runs should produce the MOCKED message, not the success message."""
    # Use check_interference (a mocked tool) to trigger the mocked-only branch.
    session_row = {
        "user_goal": "demo",
        "source_mode": "plan",
        "accepted_family": None,
        "metadata_json": json.dumps({"workflow_mode": "edit_existing", "active_model_path": "/model.sldprt"}),
    }
    checkpoints = [
        {
            "id": 2,
            "checkpoint_index": 1,
            "title": "Check",
            "executed": False,
            "planned_action_json": json.dumps({"tools": ["check_interference"]}),
        }
    ]
    merge_calls: list[dict[str, object]] = []

    from solidworks_mcp.ui.services import session_service

    monkeypatch.setattr(session_service, "ensure_dashboard_session", lambda *_a, **_kw: session_row)
    monkeypatch.setattr(service, "list_plan_checkpoints", lambda *_a, **_kw: checkpoints)

    async def _run_checkpoint(*_a, **_kw):
        return {
            "failed_tools": [],
            "mocked_tools": ["check_interference"],
            "tool_runs": [{"tool": "check_interference", "status": "mocked", "message": "mocked"}],
            "script_path": "script.py",
            "script_text": "",
            "stdout_text": "",
            "stderr_text": "",
            "validation_failures": [],
        }

    monkeypatch.setattr(service, "_run_checkpoint_tools", _run_checkpoint)
    monkeypatch.setattr(service, "update_plan_checkpoint", lambda *_a, **_kw: None)
    monkeypatch.setattr(service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(service, "upsert_design_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw))
    monkeypatch.setattr(session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True})

    result = await service.execute_next_checkpoint("s1")

    assert result == {"ok": True}
    assert any("MOCKED" in call.get("latest_message", "") for call in merge_calls)


def test_should_open_empty_part_conditions() -> None:
    """_should_open_empty_part should respect all early-return conditions."""
    # Various session states that prevent opening an empty part.
    base_meta = {"workflow_mode": "new_design", "active_model_path": "", "new_design_part_opened": False}
    sketch_planned = {"tools": ["create_sketch"]}

    # True when all conditions permit.
    assert service._should_open_empty_part(base_meta, sketch_planned) is True

    # False when workflow_mode is not new_design.
    assert service._should_open_empty_part({**base_meta, "workflow_mode": "edit_existing"}, sketch_planned) is False

    # False when active_model_path is non-empty.
    assert service._should_open_empty_part({**base_meta, "active_model_path": "/model.sldprt"}, sketch_planned) is False

    # False when new_design_part_opened is True.
    assert service._should_open_empty_part({**base_meta, "new_design_part_opened": True}, sketch_planned) is False

    # False when tools include create_part/create_assembly/open_model.
    assert service._should_open_empty_part(base_meta, {"tools": ["create_part"]}) is False
    assert service._should_open_empty_part(base_meta, {"tools": ["open_model"]}) is False


@pytest.mark.asyncio
async def test_open_empty_part_create_part_failure(monkeypatch, tmp_path) -> None:
    """create_part failures in _open_empty_part_before_checkpoint should raise."""
    # Exercise the RuntimeError path when create_part returns is_success=False.

    class FailAdapter:
        async def connect(self):
            pass

        async def create_part(self, **_kw):
            return SimpleNamespace(is_success=False, error="COM error")

        async def disconnect(self):
            pass

    async def _create_adapter(_cfg):
        return FailAdapter()

    monkeypatch.setattr(service, "create_adapter", _create_adapter)
    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "merge_metadata", lambda *_a, **_kw: None)
    monkeypatch.setattr(service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(service, "ensure_preview_dir", lambda: tmp_path)

    # The function should propagate the RuntimeError raised internally.
    with pytest.raises(RuntimeError, match="Failed to open blank part|COM error"):
        await service._open_empty_part_before_checkpoint(
            session_id="s1",
            session_row={"user_goal": "demo"},
            db_path=None,
            api_origin="http://localhost",
        )


@pytest.mark.asyncio
async def test_open_empty_part_disconnect_raises(monkeypatch, tmp_path) -> None:
    """Disconnect errors in _open_empty_part_before_checkpoint should be swallowed."""
    # Exercise the except-in-finally at lines 190-191.
    from solidworks_mcp.ui.services import preview_service

    class DisconnectRaisesAdapter:
        async def connect(self):
            pass

        async def create_part(self, **_kw):
            return SimpleNamespace(is_success=True, error="")

        async def disconnect(self):
            raise RuntimeError("disconnect failed")

    async def _create_adapter(_cfg):
        return DisconnectRaisesAdapter()

    async def _refresh_preview(*_a, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "create_adapter", _create_adapter)
    monkeypatch.setattr(service, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "merge_metadata", lambda *_a, **_kw: None)
    monkeypatch.setattr(service, "insert_tool_call_record", lambda **_kw: None)
    monkeypatch.setattr(service, "ensure_preview_dir", lambda: tmp_path)
    monkeypatch.setattr(preview_service, "refresh_preview", _refresh_preview)

    # Disconnect exception is swallowed; result should still be success.
    result = await service._open_empty_part_before_checkpoint(
        session_id="s1",
        session_row={"user_goal": "demo"},
        db_path=None,
        api_origin="http://localhost",
    )
    assert result["status"] == "success"


def test_planned_tool_payloads_direct_dict_and_suffix() -> None:
    """_planned_tool_payloads should include direct dict and suffixed payloads."""
    # Cover the direct-dict and suffixed-key branches.
    planned = {
        "create_part": {"part_name": "base"},
        "create_part#2": {"part_name": "second"},
        "other": "ignored",
    }
    payloads = service._planned_tool_payloads(planned, "create_part")
    assert len(payloads) == 2
    assert payloads[0]["part_name"] == "base"
    assert payloads[1]["part_name"] == "second"


def test_pf_handles_non_float_value() -> None:
    """_pf should skip keys with non-numeric values and return the default."""
    # Covers the except branch in _pf when the value can't be converted.
    result = service._pf({"key": "not-a-float"}, "key", default=5.0)
    assert result == 5.0


def test_pv_handles_wrong_element_types() -> None:
    """_pv should skip lists with non-numeric elements and return default."""
    # Covers the except branch in _pv when list elements can't be converted.
    result = service._pv({"key": ["a", "b", "c", "d"]}, "key", size=4, default=[1.0, 2.0, 3.0, 4.0])
    assert result == [1.0, 2.0, 3.0, 4.0]
