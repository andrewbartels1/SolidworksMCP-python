"""Tests for the Prefab dashboard service helpers."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.solidworks_mcp.agents.history_db import (
    get_design_session,
    insert_model_state_snapshot,
    list_tool_call_records,
    upsert_design_session,
)
from src.solidworks_mcp.ui.service import (
    DEFAULT_SESSION_ID,
    build_dashboard_state,
    connect_target_model,
    ensure_dashboard_session,
    execute_next_checkpoint,
    ingest_reference_source,
    reconcile_manual_edits,
    select_workflow_mode,
    update_ui_preferences,
)


class _DummyAdapterResult:
    def __init__(self, *, is_success: bool = True, data=None, error: str | None = None):
        self.is_success = is_success
        self.data = data
        self.error = error
        self.execution_time = 0.01


class _DummyAdapter:
    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def open_model(self, file_path: str) -> _DummyAdapterResult:
        return _DummyAdapterResult(
            data={
                "name": Path(file_path).name,
                "type": "Part",
                "path": file_path,
                "configuration": "Default",
            }
        )

    async def get_model_info(self) -> _DummyAdapterResult:
        return _DummyAdapterResult(
            data={"type": "Part", "configuration": "Default", "name": "part_1"}
        )

    async def list_features(
        self, include_suppressed: bool = True
    ) -> _DummyAdapterResult:
        return _DummyAdapterResult(
            data=[
                {"name": "Boss-Extrude1", "type": "Boss-Extrude", "suppressed": False},
                {"name": "Sketch1", "type": "ProfileFeature", "suppressed": False},
            ]
        )

    async def export_image(self, payload: dict[str, object]) -> _DummyAdapterResult:
        file_path = Path(str(payload["file_path"]))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"preview")
        return _DummyAdapterResult(data={"file_path": str(file_path)})


def test_ensure_dashboard_session_seeds_default_checkpoints(tmp_path: Path) -> None:
    db_path = tmp_path / "ui.sqlite3"

    state = build_dashboard_state(DEFAULT_SESSION_ID, db_path=db_path)

    assert state["session_id"] == DEFAULT_SESSION_ID
    assert len(state["checkpoints"]) == 4
    assert state["checkpoints"][0]["status"] == "approved"


@pytest.mark.asyncio
async def test_execute_next_checkpoint_updates_tool_log(tmp_path: Path) -> None:
    db_path = tmp_path / "ui.sqlite3"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    state = await execute_next_checkpoint(DEFAULT_SESSION_ID, db_path=db_path)
    records = list_tool_call_records(DEFAULT_SESSION_ID, db_path=db_path)

    assert state["checkpoints"][0]["status"] == "executed"
    assert records[-1]["tool_name"] == "add_line"


def test_reconcile_manual_edits_reports_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "ui.sqlite3"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    insert_model_state_snapshot(
        session_id=DEFAULT_SESSION_ID,
        screenshot_path=str(tmp_path / "before.png"),
        state_fingerprint="before",
        db_path=db_path,
    )
    insert_model_state_snapshot(
        session_id=DEFAULT_SESSION_ID,
        screenshot_path=str(tmp_path / "after.png"),
        state_fingerprint="after",
        db_path=db_path,
    )

    state = reconcile_manual_edits(DEFAULT_SESSION_ID, db_path=db_path)

    assert "Detected manual changes" in state["latest_message"]


def test_update_preferences_persists_model_and_assumptions(tmp_path: Path) -> None:
    db_path = tmp_path / "ui.sqlite3"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    state = update_ui_preferences(
        DEFAULT_SESSION_ID,
        assumptions_text="Assume 0.25mm clearance and PETG material.",
        model_provider="local",
        model_profile="small",
        model_name="",
        local_endpoint="http://127.0.0.1:11434/v1",
        db_path=db_path,
    )

    assert state["assumptions_text"].startswith("Assume 0.25mm clearance")
    assert state["model_provider"] == "local"
    assert state["model_profile"] == "small"
    assert state["model_name"] == "local:google/gemma-3-4b-it"
    assert "Readiness" in state["readiness_summary"]


def test_select_workflow_mode_persists_opening_branch(tmp_path: Path) -> None:
    db_path = tmp_path / "ui.sqlite3"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    state = select_workflow_mode(
        DEFAULT_SESSION_ID,
        workflow_mode="edit_existing",
        db_path=db_path,
    )

    assert state["workflow_mode"] == "edit_existing"
    assert state["workflow_label"] == "Editing Existing Part or Assembly"
    assert "Attach Model" in state["flow_header_text"]


def test_build_dashboard_state_sanitizes_corrupted_ui_metadata(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ui.sqlite3"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)
    session_row = get_design_session(DEFAULT_SESSION_ID, db_path=db_path)
    assert session_row is not None

    corrupted_metadata = {
        "workflow_mode": "edit_existing",
        "active_model_path": str(tmp_path / "part_1.sldprt"),
        "workflow_label": "{{ $result.workflow_label }}",
        "flow_header_text": "{{ $result.flow_header_text }}",
        "workflow_guidance_text": "{{ $result.workflow_guidance_text }}",
        "model_name": "{{ $result.model_name }}",
        "local_endpoint": "{{ $result.local_endpoint }}",
        "assumptions_text": "{{ $result.assumptions_text }}",
        "preview_viewer_url": "http://127.0.0.1:5175/",
    }

    upsert_design_session(
        session_id=DEFAULT_SESSION_ID,
        user_goal=session_row["user_goal"],
        source_mode=session_row["source_mode"],
        accepted_family=session_row["accepted_family"],
        status=session_row["status"],
        current_checkpoint_index=session_row["current_checkpoint_index"],
        metadata_json=json.dumps(corrupted_metadata, ensure_ascii=True),
        db_path=db_path,
    )

    state = build_dashboard_state(
        DEFAULT_SESSION_ID,
        db_path=db_path,
        api_origin="http://127.0.0.1:8766",
    )

    assert state["workflow_label"] == "Editing Existing Part or Assembly"
    assert "Attach Model" in state["flow_header_text"]
    assert "existing SolidWorks file" in state["workflow_guidance_text"]
    assert "$result" not in state["model_name"]
    assert state["model_name"]
    assert "$result" not in state["local_endpoint"]
    assert state["local_endpoint"] == "http://127.0.0.1:11434/v1"
    assert "$result" not in state["assumptions_text"]
    assert state["preview_viewer_url"] == (
        "http://127.0.0.1:8766/api/ui/viewer/prefab-dashboard"
        "?session_id=prefab-dashboard&t=0"
    )


@pytest.mark.asyncio
async def test_connect_target_model_persists_active_model_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "ui.sqlite3"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)
    part_path = tmp_path / "part_1.sldprt"
    part_path.write_text("solidworks placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "src.solidworks_mcp.ui.service.load_config", lambda: SimpleNamespace()
    )

    async def _fake_create_adapter(config):
        return _DummyAdapter()

    monkeypatch.setattr(
        "src.solidworks_mcp.ui.service.create_adapter", _fake_create_adapter
    )

    state = await connect_target_model(
        DEFAULT_SESSION_ID,
        model_path=str(part_path),
        feature_target_text="@Boss-Extrude1",
        db_path=db_path,
    )

    assert state["active_model_path"] == str(part_path)
    assert state["workflow_mode"] == "edit_existing"
    assert "Attached model" in state["active_model_status"]
    assert state["proposed_family"] == "extrude"
    assert "@Boss-Extrude1" in state["feature_target_status"]


@pytest.mark.asyncio
async def test_connect_target_model_accepts_uploaded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "ui.sqlite3"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    monkeypatch.setattr(
        "src.solidworks_mcp.ui.service.load_config", lambda: SimpleNamespace()
    )

    async def _fake_create_adapter(config):
        return _DummyAdapter()

    monkeypatch.setattr(
        "src.solidworks_mcp.ui.service.create_adapter", _fake_create_adapter
    )

    state = await connect_target_model(
        DEFAULT_SESSION_ID,
        uploaded_files=[
            {
                "name": "uploaded_part.sldprt",
                "size": 12,
                "type": "application/octet-stream",
                "data": base64.b64encode(b"solidworks binary").decode("ascii"),
            }
        ],
        feature_target_text="@Boss-Extrude1",
        db_path=db_path,
    )

    uploaded_path = Path(state["active_model_path"])
    assert uploaded_path.exists()
    assert uploaded_path.name == "uploaded_part.sldprt"
    assert state["workflow_mode"] == "edit_existing"
    assert state["proposed_family"] == "extrude"


def test_ingest_reference_source_builds_local_index(tmp_path: Path) -> None:
    db_path = tmp_path / "ui.sqlite3"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)
    source_path = tmp_path / "how-to.md"
    source_path.write_text(
        "Step 1: Create a sketch.\nStep 2: Extrude the profile.", encoding="utf-8"
    )

    state = ingest_reference_source(
        DEFAULT_SESSION_ID,
        source_path=str(source_path),
        namespace="box-howto",
        db_path=db_path,
    )

    assert state["rag_namespace"] == "box-howto"
    assert state["rag_chunk_count"] >= 1
    assert Path(state["rag_index_path"]).exists()


def test_ingest_reference_source_accepts_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "ui.sqlite3"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    monkeypatch.setattr(
        "src.solidworks_mcp.ui.service._read_reference_url",
        lambda source_url: ("Remote guide text for planning.", "guide.html"),
    )

    state = ingest_reference_source(
        DEFAULT_SESSION_ID,
        source_path="https://example.com/guide.html",
        namespace="remote-howto",
        db_path=db_path,
    )

    assert state["rag_namespace"] == "remote-howto"
    assert state["rag_source_path"] == "https://example.com/guide.html"
    assert state["rag_chunk_count"] >= 1
    assert Path(state["rag_index_path"]).exists()
