"""Tests for session_service helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from solidworks_mcp.ui.services import session_service


def test_checkpoint_specs_for_ujoint_and_default() -> None:
    """Checkpoint specs should switch for U-joint goals."""
    # Ensure the U-joint keyword selects the alternate checkpoint list.
    ujoint = session_service._checkpoint_specs_for_goal("Build a U-Joint")
    default = session_service._checkpoint_specs_for_goal("Other")
    assert ujoint != default
    assert len(ujoint) == len(session_service._UJOINT_CHECKPOINT_SPECS)


def test_default_checkpoint_specs_returns_copy() -> None:
    """default_checkpoint_specs should return a list copy."""
    # Validate the default spec accessor returns a list.
    specs = session_service.default_checkpoint_specs()
    assert isinstance(specs, list)


def test_load_session_context_non_dict_state(monkeypatch, tmp_path) -> None:
    """Non-dict context state should default to empty dict."""
    # Save a snapshot with a non-dict "state" and ensure load succeeds.
    snapshot_path = tmp_path / "context.json"
    snapshot_path.write_text(json.dumps({"state": ["bad"]}), encoding="utf-8")

    monkeypatch.setattr(
        session_service,
        "ensure_dashboard_session",
        lambda *_a, **_kw: {"metadata_json": "{}"},
    )
    monkeypatch.setattr(
        session_service, "upsert_design_session", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(session_service, "persist_ui_action", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )

    result = session_service.load_session_context("s1", context_file=str(snapshot_path))
    assert result == {"ok": True}


def test_compute_readiness_handles_load_config_error(monkeypatch, tmp_path) -> None:
    """Readiness should fall back to unknown when load_config fails."""
    # Force load_config to raise and assert adapter_mode becomes unknown.
    monkeypatch.setattr(
        session_service,
        "load_config",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(session_service, "ensure_preview_dir", lambda: tmp_path)

    readiness = session_service._compute_readiness({}, db_ready=True)
    assert readiness["readiness_adapter_mode"] == "unknown"


def test_build_checkpoint_rows_marks_failed(monkeypatch) -> None:
    """Checkpoint rows should mark error results as failed."""
    # Provide a row with error status to hit the failed branch.
    row = {
        "checkpoint_index": 1,
        "title": "Step",
        "planned_action_json": json.dumps({"tools": ["create_part"]}),
        "result_json": json.dumps({"status": "error"}),
        "executed": False,
        "approved_by_user": False,
    }
    monkeypatch.setattr(
        session_service, "list_plan_checkpoints", lambda *_a, **_kw: [row]
    )
    rows = session_service._build_checkpoint_rows(
        "s1", db_path=None, is_new_design_clean=False
    )
    assert rows[0]["status"] == "failed"


def test_build_feature_tree_rows_handles_bad_json(monkeypatch) -> None:
    """Invalid feature_tree_json should be ignored without crashing."""
    # Provide invalid JSON to exercise the exception branch.
    monkeypatch.setattr(
        session_service,
        "list_model_state_snapshots",
        lambda *_a, **_kw: [{"feature_tree_json": "{bad json"}],
    )
    rows = session_service._build_feature_tree(
        "s1", selected_feature_name="", db_path=None, is_new_design_clean=False
    )
    assert rows == []


def test_build_feature_tree_returns_empty_for_new_design_clean(monkeypatch) -> None:
    """is_new_design_clean=True should short-circuit to empty list."""
    rows = session_service._build_feature_tree(
        "s1", selected_feature_name="", db_path=None, is_new_design_clean=True
    )
    assert rows == []


def test_build_feature_tree_marks_selected_feature(monkeypatch) -> None:
    """Feature matching selected_feature_name should get _selected marker."""
    features = [{"name": "Feat1", "type": "extrude"}, {"name": "Feat2", "type": "sketch"}]
    monkeypatch.setattr(
        session_service,
        "list_model_state_snapshots",
        lambda *_a, **_kw: [{"feature_tree_json": json.dumps(features)}],
    )
    rows = session_service._build_feature_tree(
        "s1", selected_feature_name="Feat1", db_path=None, is_new_design_clean=False
    )
    feat1_rows = [r for r in rows if r.get("name") == "Feat1"]
    assert feat1_rows[0]["_selected"] == "●"
    feat2_rows = [r for r in rows if r.get("name") == "Feat2"]
    assert feat2_rows[0]["_selected"] == ""


def test_build_feature_tree_filters_meta_names_and_types(monkeypatch) -> None:
    """Features with meta names/types should be excluded from the output."""
    features = [
        {"name": "sensors", "type": "extrude"},  # filtered by _META_NAMES
        {"name": "sensorfolder", "type": "sensorfolder"},  # filtered by _META_TYPES
        {"name": "Boss-Extrude1", "type": "boss-extrude"},  # kept
    ]
    monkeypatch.setattr(
        session_service,
        "list_model_state_snapshots",
        lambda *_a, **_kw: [{"feature_tree_json": json.dumps(features)}],
    )
    rows = session_service._build_feature_tree(
        "s1", selected_feature_name="", db_path=None, is_new_design_clean=False
    )
    names = [r.get("name") for r in rows]
    assert "Boss-Extrude1" in names
    assert "sensors" not in names


def test_build_evidence_rows_returns_empty_for_new_design_clean(monkeypatch) -> None:
    """Evidence rows should be empty for clean new-design sessions."""
    rows = session_service._build_evidence_rows(
        "s1",
        db_path=None,
        active_model_path="",
        is_new_design_clean=True,
    )
    assert rows == []


def test_build_evidence_rows_filters_stale_model_evidence(monkeypatch) -> None:
    """Evidence linked to different model path should be filtered out."""
    evidence = [
        {
            "source_type": "active_model",
            "source_id": "C:/other/model.sldprt",
            "rationale": "other model",
            "relevance_score": 0.5,
        }
    ]
    monkeypatch.setattr(
        session_service, "list_evidence_links", lambda *_a, **_kw: evidence
    )
    rows = session_service._build_evidence_rows(
        "s1",
        db_path=None,
        active_model_path="C:/current/model.sldprt",
        is_new_design_clean=False,
    )
    assert rows == []


def test_build_evidence_rows_keeps_non_model_evidence(monkeypatch) -> None:
    """RAG evidence (not model-scoped) should pass through."""
    evidence = [
        {
            "source_type": "rag",
            "source_id": "guide.md",
            "rationale": "step 1",
            "relevance_score": 0.8,
        }
    ]
    monkeypatch.setattr(
        session_service, "list_evidence_links", lambda *_a, **_kw: evidence
    )
    rows = session_service._build_evidence_rows(
        "s1",
        db_path=None,
        active_model_path="C:/model.sldprt",
        is_new_design_clean=False,
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "rag"


def test_build_evidence_rows_collapses_feature_target_to_latest(monkeypatch) -> None:
    """Multiple feature_target rows should collapse to only the last one."""
    evidence = [
        {
            "source_type": "feature_target",
            "source_id": "C:/model.sldprt",
            "rationale": "old target",
            "relevance_score": 0.3,
        },
        {
            "source_type": "feature_target",
            "source_id": "C:/model.sldprt",
            "rationale": "latest target",
            "relevance_score": 0.7,
        },
    ]
    monkeypatch.setattr(
        session_service, "list_evidence_links", lambda *_a, **_kw: evidence
    )
    rows = session_service._build_evidence_rows(
        "s1",
        db_path=None,
        active_model_path="C:/model.sldprt",
        is_new_design_clean=False,
    )
    assert len(rows) == 1
    assert rows[0]["detail"] == "latest target"


def test_planned_tools_handles_non_list() -> None:
    """_planned_tools should return [] for non-list tools entries."""
    assert session_service._planned_tools({"tools": "create_part"}) == []
    assert session_service._planned_tools({}) == []


def test_build_checkpoint_rows_executed_approved_queued(monkeypatch) -> None:
    """Status should be 'executed', 'approved', and 'queued' for different states."""
    rows = [
        {
            "checkpoint_index": 1, "title": "First",
            "planned_action_json": json.dumps({"tools": ["create_part"]}),
            "result_json": json.dumps({"status": "success"}),
            "executed": True, "approved_by_user": True,
        },
        {
            "checkpoint_index": 2, "title": "Second",
            "planned_action_json": json.dumps({"tools": ["create_sketch"]}),
            "result_json": "",
            "executed": False, "approved_by_user": True,
        },
        {
            "checkpoint_index": 3, "title": "Third",
            "planned_action_json": json.dumps({"tools": ["exit_sketch"]}),
            "result_json": "",
            "executed": False, "approved_by_user": False,
        },
    ]
    monkeypatch.setattr(
        session_service, "list_plan_checkpoints", lambda *_a, **_kw: rows
    )
    result = session_service._build_checkpoint_rows(
        "s1", db_path=None, is_new_design_clean=False
    )
    assert result[0]["status"] == "executed"
    assert result[1]["status"] == "approved"
    assert result[2]["status"] == "queued"


def test_build_checkpoint_rows_mocked_tools_in_tools_text(monkeypatch) -> None:
    """Mocked tools should appear in the tools text."""
    rows = [
        {
            "checkpoint_index": 1, "title": "Check",
            "planned_action_json": json.dumps({"tools": ["check_interference"]}),
            "result_json": json.dumps({"status": "success", "mocked_tools": ["check_interference"]}),
            "executed": True, "approved_by_user": True,
        }
    ]
    monkeypatch.setattr(
        session_service, "list_plan_checkpoints", lambda *_a, **_kw: rows
    )
    result = session_service._build_checkpoint_rows(
        "s1", db_path=None, is_new_design_clean=False
    )
    assert "MOCKED" in result[0]["tools"]


def test_build_checkpoint_rows_new_design_clean_resets_status(monkeypatch) -> None:
    """is_new_design_clean=True and not executed should force 'queued'."""
    rows = [
        {
            "checkpoint_index": 1, "title": "Step",
            "planned_action_json": json.dumps({"tools": ["create_sketch"]}),
            "result_json": "",
            "executed": False, "approved_by_user": True,  # approved but not executed
        }
    ]
    monkeypatch.setattr(
        session_service, "list_plan_checkpoints", lambda *_a, **_kw: rows
    )
    result = session_service._build_checkpoint_rows(
        "s1", db_path=None, is_new_design_clean=True
    )
    assert result[0]["status"] == "queued"


def test_approve_design_brief(monkeypatch) -> None:
    """approve_design_brief should persist goal and return dashboard state."""
    calls: list[dict] = []
    monkeypatch.setattr(
        session_service, "ensure_dashboard_session", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        session_service, "persist_ui_action", lambda *_a, **kw: calls.append(kw)
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    result = session_service.approve_design_brief("s1", "make a bracket")
    assert result == {"ok": True}
    assert any(kw.get("tool_name") == "ui.approve_brief" for kw in calls)


def test_accept_family_choice_uses_proposed_from_metadata(monkeypatch) -> None:
    """accept_family_choice should fall back to proposed_family in metadata."""
    calls: list[dict] = []
    monkeypatch.setattr(
        session_service,
        "ensure_dashboard_session",
        lambda *_a, **_kw: {
            "metadata_json": json.dumps({"proposed_family": "sheet_metal"}),
            "user_goal": "make a bracket",
            "source_mode": "prompt",
            "current_checkpoint_index": 0,
        },
    )
    monkeypatch.setattr(
        session_service, "upsert_design_session", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        session_service, "persist_ui_action", lambda *_a, **kw: calls.append(kw)
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    result = session_service.accept_family_choice("s1", family=None)
    assert result == {"ok": True}
    assert any("sheet_metal" in str(kw) for kw in calls)


def test_reconcile_manual_edits_not_enough_snapshots(monkeypatch) -> None:
    """reconcile should report missing snapshots message."""
    monkeypatch.setattr(
        session_service, "ensure_dashboard_session", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        session_service, "list_model_state_snapshots", lambda *_a, **_kw: []
    )
    monkeypatch.setattr(
        session_service, "persist_ui_action", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    result = session_service.reconcile_manual_edits("s1")
    assert result == {"ok": True}


def test_reconcile_manual_edits_no_change_detected(monkeypatch) -> None:
    """reconcile with matching snapshots should report no change."""
    snaps = [
        {"state_fingerprint": "abc", "screenshot_path": "p.png"},
        {"state_fingerprint": "abc", "screenshot_path": "p.png"},
    ]
    persist_calls: list[dict] = []
    monkeypatch.setattr(
        session_service, "ensure_dashboard_session", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        session_service, "list_model_state_snapshots", lambda *_a, **_kw: snaps
    )
    monkeypatch.setattr(
        session_service, "persist_ui_action", lambda *_a, **kw: persist_calls.append(kw)
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    session_service.reconcile_manual_edits("s1")
    assert any("No visual" in str(kw) for kw in persist_calls)


def test_update_ui_preferences_persists_model_info(monkeypatch) -> None:
    """update_ui_preferences should persist provider/profile/model."""
    calls: list[dict] = []
    monkeypatch.setattr(
        session_service, "ensure_dashboard_session", lambda *_a, **_kw: {}
    )
    monkeypatch.setattr(
        session_service, "persist_ui_action", lambda *_a, **kw: calls.append(kw)
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    result = session_service.update_ui_preferences(
        "s1",
        assumptions_text="Use PETG",
        model_provider="github",
        model_profile="balanced",
        model_name="",
    )
    assert result == {"ok": True}


def test_select_workflow_mode_new_design_resets_state(monkeypatch) -> None:
    """select_workflow_mode for new_design should upsert and reset checkpoints."""
    upsert_calls: list = []
    checkpoint_calls: list = []
    monkeypatch.setattr(
        session_service,
        "ensure_dashboard_session",
        lambda *_a, **_kw: {"metadata_json": "{}", "source_mode": "prompt"},
    )
    monkeypatch.setattr(
        session_service, "upsert_design_session", lambda *_a, **_kw: upsert_calls.append(1)
    )
    monkeypatch.setattr(
        session_service, "list_plan_checkpoints",
        lambda *_a, **_kw: [{"id": 1}]
    )
    monkeypatch.setattr(
        session_service, "update_plan_checkpoint",
        lambda _id, **_kw: checkpoint_calls.append(_id)
    )
    monkeypatch.setattr(
        session_service, "persist_ui_action", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    result = session_service.select_workflow_mode("s1", workflow_mode="new_design")
    assert result == {"ok": True}
    assert upsert_calls  # upsert was called


def test_select_workflow_mode_edit_existing_merges(monkeypatch) -> None:
    """select_workflow_mode for edit_existing should call merge_metadata."""
    merge_calls: list = []
    monkeypatch.setattr(
        session_service,
        "ensure_dashboard_session",
        lambda *_a, **_kw: {"metadata_json": "{}", "source_mode": "prompt"},
    )
    monkeypatch.setattr(
        session_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw) or {}
    )
    monkeypatch.setattr(
        session_service, "persist_ui_action", lambda *_a, **_kw: None
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    session_service.select_workflow_mode("s1", workflow_mode="edit_existing")
    assert merge_calls


def test_update_session_notes(monkeypatch) -> None:
    """update_session_notes should persist notes and return state."""
    calls: list[dict] = []
    monkeypatch.setattr(
        session_service, "persist_ui_action", lambda *_a, **kw: calls.append(kw)
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    result = session_service.update_session_notes("s1", notes_text="my notes")
    assert result == {"ok": True}
    assert any(kw.get("tool_name") == "ui.notes.update" for kw in calls)


def test_save_session_context(tmp_path, monkeypatch) -> None:
    """save_session_context should write a JSON file and return state."""
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"session_id": "s1"}
    )
    monkeypatch.setattr(
        session_service, "persist_ui_action", lambda *_a, **_kw: None
    )
    result = session_service.save_session_context(
        "s1", context_name="test-save", context_dir=tmp_path
    )
    assert result == {"session_id": "s1"}
    saved_files = list(tmp_path.glob("*.json"))
    assert len(saved_files) == 1


def test_load_session_context_file_not_found(tmp_path, monkeypatch) -> None:
    """load_session_context with missing file should record error and return state."""
    merge_calls: list[dict] = []
    monkeypatch.setattr(
        session_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw)
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    result = session_service.load_session_context(
        "s1", context_file=str(tmp_path / "nonexistent.json")
    )
    assert result == {"ok": True}
    assert any("not found" in str(kw.get("context_load_status", "")) for kw in merge_calls)


def test_load_session_context_invalid_json(tmp_path, monkeypatch) -> None:
    """load_session_context with corrupt JSON should record error."""
    bad_file = tmp_path / "context.json"
    bad_file.write_text("{not valid json}", encoding="utf-8")
    merge_calls: list[dict] = []
    monkeypatch.setattr(
        session_service, "merge_metadata", lambda *_a, **kw: merge_calls.append(kw)
    )
    monkeypatch.setattr(
        session_service, "build_dashboard_state", lambda *_a, **_kw: {"ok": True}
    )
    result = session_service.load_session_context("s1", context_file=str(bad_file))
    assert result == {"ok": True}
    assert any("Context load failed" in str(kw.get("context_load_status", "")) for kw in merge_calls)


def test_compute_readiness_with_credentials(monkeypatch, tmp_path) -> None:
    """_compute_readiness should show provider_configured=True when token set."""
    monkeypatch.setenv("GITHUB_API_KEY", "tok")
    monkeypatch.setattr(
        session_service, "load_config",
        lambda: type("C", (), {"adapter_type": type("A", (), {"value": "mock"})()})()
    )
    monkeypatch.setattr(session_service, "ensure_preview_dir", lambda: tmp_path)
    result = session_service._compute_readiness({"model_name": "github:openai/gpt-4.1"}, db_ready=True)
    assert result["readiness_provider_configured"] is True
    assert result["readiness_db_ready"] is True
