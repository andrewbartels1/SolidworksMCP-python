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
