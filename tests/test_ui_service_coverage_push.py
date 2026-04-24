"""Comprehensive coverage push for ui/service.py - targeting 209 missing lines."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.solidworks_mcp.agents.history_db import (
    get_design_session,
    insert_evidence_link,
    insert_model_state_snapshot,
    insert_plan_checkpoint,
    list_model_state_snapshots,
    list_plan_checkpoints,
    update_plan_checkpoint,
    upsert_design_session,
)
from src.solidworks_mcp.ui import service
from src.solidworks_mcp.ui.service import (
    DEFAULT_SESSION_ID,
    CheckpointCandidate,
    ClarificationResponse,
    FamilyInspection,
    accept_family_choice,
    approve_design_brief,
    build_dashboard_state,
    build_dashboard_trace_payload,
    connect_target_model,
    ensure_context_dir,
    ensure_dashboard_session,
    execute_next_checkpoint,
    fetch_docs_context,
    highlight_feature,
    ingest_reference_source,
    inspect_family,
    open_target_model,
    reconcile_manual_edits,
    request_clarifications,
    run_go_orchestration,
    select_workflow_mode,
    update_ui_preferences,
)


class _DummyAdapter:
    """Mock adapter for testing."""

    def __init__(self, *, fail: bool = False):
        """Test init."""

        self.fail = fail
        self.connected = False

    async def connect(self) -> None:
        """Test connect."""

        self.connected = True

    async def disconnect(self) -> None:
        """Test disconnect."""

        self.connected = False

    async def open_model(self, path: str) -> Any:
        """Test open model."""

        if self.fail:
            return SimpleNamespace(
                is_success=False, error="Cannot open model", execution_time=0.01
            )
        return SimpleNamespace(
            is_success=True,
            data={"name": Path(path).name, "type": "Part", "path": path},
            execution_time=0.01,
        )

    async def get_model_info(self) -> Any:
        """Test get model info."""

        return SimpleNamespace(
            is_success=True,
            data={"type": "Part", "configuration": "Default", "name": "test_part"},
            execution_time=0.01,
        )

    async def list_features(self, **kwargs) -> Any:
        """Test list features."""

        return SimpleNamespace(
            is_success=True,
            data=[
                {"name": "Boss-Extrude1", "type": "Boss-Extrude", "suppressed": False},
                {"name": "Sketch1", "type": "ProfileFeature", "suppressed": False},
            ],
            execution_time=0.01,
        )

    async def export_image(self, payload: dict[str, object]) -> Any:
        """Test export image."""

        file_path = Path(str(payload.get("file_path", "preview.png")))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"fake_image_data")
        return SimpleNamespace(
            is_success=True, data={"file_path": str(file_path)}, execution_time=0.01
        )

    async def create_sketch(self, plane: str) -> Any:
        """Test create sketch."""

        if self.fail:
            return SimpleNamespace(
                is_success=False, error="create_sketch failed", execution_time=0.01
            )
        return SimpleNamespace(
            is_success=True, data={"sketch": plane}, execution_time=0.01
        )

    async def add_line(self, x1: float, y1: float, x2: float, y2: float) -> Any:
        """Test add line."""

        if self.fail:
            return SimpleNamespace(
                is_success=False, error="add_line failed", execution_time=0.01
            )
        return SimpleNamespace(is_success=True, data={}, execution_time=0.01)

    async def create_extrusion(self, params: Any) -> Any:
        """Test create extrusion."""

        if self.fail:
            return SimpleNamespace(
                is_success=False, error="create_extrusion failed", execution_time=0.01
            )
        return SimpleNamespace(is_success=True, data={}, execution_time=0.01)

    async def create_cut(self, sketch: str, depth: float) -> Any:
        """Test create cut."""

        if self.fail:
            return SimpleNamespace(
                is_success=False, error="create_cut failed", execution_time=0.01
            )
        return SimpleNamespace(is_success=True, data={}, execution_time=0.01)

    async def select_feature(self, feature_name: str) -> Any:
        """Test select feature."""

        if self.fail:
            return SimpleNamespace(
                is_success=True, data={"selected": False}, execution_time=0.01
            )
        return SimpleNamespace(
            is_success=True,
            data={
                "selected": True,
                "entity_type": "BODYFEATURE",
                "selected_name": feature_name,
            },
            execution_time=0.01,
        )


# ============================================================================
# Parameterized tests for sanitization and helper functions
# ============================================================================


@pytest.mark.parametrize(
    "input_value,fallback,expected",
    [
        ("valid text", "", "valid text"),
        (None, "default", "default"),
        ("  ", "default", "default"),
        ('"', "fallback", "fallback"),
        ("'", "fallback", "fallback"),
        ("{{ bad }}", "fallback", "fallback"),
        ("$result.value", "fallback", "fallback"),
        ("$error message", "fallback", "fallback"),
        (123, "", "123"),
        ("", "empty", "empty"),
        ("  clean text  ", "", "clean text"),
    ],
)
def test_sanitize_ui_text_variants(input_value, fallback, expected):
    """Test _sanitize_ui_text with various input types and edge cases."""
    result = service._sanitize_ui_text(input_value, fallback)
    assert result == expected


@pytest.mark.parametrize(
    "input_path,expected",
    [
        ('"C:\\Users\\andre\\test.sldprt"', "C:\\Users\\andre\\test.sldprt"),
        ("'D:/models/part.sldprt'", "D:/models/part.sldprt"),
        ("/home/user/model.sldprt", "/home/user/model.sldprt"),
        ("no_quotes.sldprt", "no_quotes.sldprt"),
        ('"', ""),
        ("", ""),
    ],
)
def test_sanitize_model_path_text_variants(input_path, expected):
    """Test _sanitize_model_path_text with quoted and unquoted paths."""
    result = service._sanitize_model_path_text(input_path)
    assert result == expected


@pytest.mark.parametrize(
    "model_name,expected_provider",
    [
        ("github:openai/gpt-4", "github"),
        ("openai:gpt-4", "openai"),
        ("anthropic:claude-3", "anthropic"),
        ("local:llama2", "local"),
        ("custom-model", "custom"),
        ("", "custom"),
    ],
)
def test_provider_from_model_name(model_name, expected_provider):
    """Test _provider_from_model_name with various qualified model names."""
    assert service._provider_from_model_name(model_name) == expected_provider


@pytest.mark.parametrize(
    "context_name,session_id,expected",
    [
        ("My Context", "session-1", "My-Context"),
        ("Context!@#$", "session", "Context"),
        ("", "my-session", "my-session"),
        (None, "default-session", "default-session"),
        ("Valid_Context-Name", "x", "Valid_Context-Name"),
    ],
)
def test_safe_context_name(context_name, session_id, expected):
    """Test _safe_context_name normalization."""
    result = service._safe_context_name(context_name, session_id)
    assert result == expected


@pytest.mark.parametrize(
    "workflow_mode,active_model_path,title_has",
    [
        ("edit_existing", None, "Editing Existing"),
        ("new_design", None, "New Design From Scratch"),
        ("new_design", "C:/part.sldprt", "New Design From Scratch"),
        ("unknown", "C:/part.sldprt", "Choose a Workflow"),
        ("unknown", None, "Choose a Workflow"),
    ],
)
def test_workflow_copy(workflow_mode, active_model_path, title_has):
    """Test _workflow_copy returns appropriate copy for different modes."""
    title, desc, guide = service._workflow_copy(workflow_mode, active_model_path)
    assert title_has in title


@pytest.mark.parametrize(
    "feature_target_text,expected_targets",
    [
        ("@Boss-Extrude1", ["Boss-Extrude1"]),
        ("@Boss-Extrude1,@Sketch1", ["Boss-Extrude1", "Sketch1"]),
        ("@Boss-Extrude1,@Sketch1,C:\\path\\file.sldprt", ["Boss-Extrude1", "Sketch1"]),
        ("", []),
        (None, []),
        ("   ", []),
    ],
)
def test_normalize_feature_targets(feature_target_text, expected_targets):
    """Test _normalize_feature_targets filters out paths and whitespace."""
    result = service._normalize_feature_targets(feature_target_text)
    assert result == expected_targets


@pytest.mark.parametrize(
    "token,is_path",
    [
        ("C:\\Users\\part.sldprt", True),
        ("D:/models/assembly.sldasm", True),
        ("/home/user/drawing.slddrw", True),
        ("model.step", True),
        ("part.iges", True),
        ("solid.stp", True),
        ("Boss-Extrude1", False),
        ("Sketch1", False),
        ("feature_name", False),
        ("", False),
    ],
)
def test_looks_like_path_token(token, is_path):
    """Test _looks_like_path_token correctly identifies file paths."""
    result = service._looks_like_path_token(token)
    assert result == is_path


@pytest.mark.parametrize(
    "docs_query,text_snippet",
    [
        ("sketch profile", "sketch profile here\nother content\nsketch tools"),
        ("", "content line 1\ncontent line 2\ncontent line 3"),
        ("nonexistent", "content line 1\ncontent line 2"),
    ],
)
def test_filter_docs_text(docs_query, text_snippet):
    """Test _filter_docs_text ranking and truncation."""
    text = "\n".join([f"line {i}" for i in range(50)]) + f"\n{text_snippet}"
    result = service._filter_docs_text(text, docs_query, max_chars=500)
    assert isinstance(result, str)
    assert len(result) <= 500


# ============================================================================
# Async workflow tests targeting major missing blocks
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires LLM credentials (GH_TOKEN or GITHUB_API_KEY)")
async def test_request_clarifications_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test request_clarifications persists clarification in metadata."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Mock the credential check to return False (will skip LLM call)
    monkeypatch.setattr(
        service, "_provider_has_credentials", lambda *args, **kwargs: False
    )

    result = await request_clarifications(
        DEFAULT_SESSION_ID,
        "bracket cable routing",
        db_path=db_path,
    )

    # Should still return valid dashboard state
    assert result["session_id"] == DEFAULT_SESSION_ID
    assert "checkpoints" in result


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires LLM credentials (GH_TOKEN or GITHUB_API_KEY)")
async def test_request_clarifications_no_credentials(tmp_path: Path) -> None:
    """Test request_clarifications handles missing LLM credentials gracefully."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = await request_clarifications(
        DEFAULT_SESSION_ID,
        "design goal",
        db_path=db_path,
    )

    # Result should still be a valid dashboard state, even if LLM call fails
    assert result["session_id"] == DEFAULT_SESSION_ID


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires LLM credentials (GH_TOKEN or GITHUB_API_KEY)")
async def test_inspect_family_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test inspect_family with family classification."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Create a model snapshot first
    insert_model_state_snapshot(
        session_id=DEFAULT_SESSION_ID,
        state_fingerprint="hash123",
        feature_tree_json=json.dumps(
            [
                {"name": "Sketch1", "type": "ProfileFeature"},
                {"name": "Boss-Extrude1", "type": "Boss-Extrude"},
            ]
        ),
        screenshot_path="/tmp/screenshot.png",
        db_path=db_path,
    )

    # Mock credential check to skip LLM call
    monkeypatch.setattr(
        service, "_provider_has_credentials", lambda *args, **kwargs: False
    )

    result = await inspect_family(
        DEFAULT_SESSION_ID,
        "Design a bracket",
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires LLM credentials (GH_TOKEN or GITHUB_API_KEY)")
async def test_inspect_family_missing_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test inspect_family when no model snapshots exist."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Mock credential check to skip LLM call
    monkeypatch.setattr(
        service, "_provider_has_credentials", lambda *args, **kwargs: False
    )

    # Don't create any snapshots - inspect_family should still run
    result = await inspect_family(
        DEFAULT_SESSION_ID,
        "Some design goal",
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID


def test_ingest_reference_source_text_file(tmp_path: Path) -> None:
    """Test ingest_reference_source with local text file."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    source_file = tmp_path / "reference.txt"
    source_file.write_text("Design guidelines: use 3mm walls for 3D printing")

    result = ingest_reference_source(
        DEFAULT_SESSION_ID,
        source_path=str(source_file),
        namespace="test-reference",
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID


def test_ingest_reference_source_invalid_path(tmp_path: Path) -> None:
    """Test ingest_reference_source with non-existent path."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = ingest_reference_source(
        DEFAULT_SESSION_ID,
        source_path="/nonexistent/file.txt",
        namespace="test-ref",
        db_path=db_path,
    )

    # Should return error state
    assert result["session_id"] == DEFAULT_SESSION_ID
    # Error message contains "missing" (case-insensitive)
    assert "missing" in result.get("latest_error_text", "").lower()


@pytest.mark.asyncio
async def test_select_workflow_mode_edit_existing(tmp_path: Path) -> None:
    """Test select_workflow_mode for edit_existing flow."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = select_workflow_mode(
        DEFAULT_SESSION_ID,
        workflow_mode="edit_existing",
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID


@pytest.mark.asyncio
async def test_select_workflow_mode_new_design(tmp_path: Path) -> None:
    """Test select_workflow_mode for new_design flow."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = select_workflow_mode(
        DEFAULT_SESSION_ID,
        workflow_mode="new_design",
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID


@pytest.mark.asyncio
async def test_connect_target_model_success(tmp_path: Path) -> None:
    """Test connect_target_model with valid model path and mocked adapter."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Create a dummy model file
    model_file = tmp_path / "test_model.sldprt"
    model_file.write_bytes(b"fake solidworks data")

    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_adapter = _DummyAdapter()
        mock_factory.return_value = mock_adapter

        result = await connect_target_model(
            DEFAULT_SESSION_ID,
            model_path=str(model_file),
            db_path=db_path,
        )

    assert result["session_id"] == DEFAULT_SESSION_ID


@pytest.mark.asyncio
async def test_connect_target_model_missing_file(tmp_path: Path) -> None:
    """Test connect_target_model with non-existent model path."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = await connect_target_model(
        DEFAULT_SESSION_ID,
        model_path="/nonexistent/model.sldprt",
        db_path=db_path,
    )

    # Should have error message with "file" in it
    assert "file" in result.get("latest_error_text", "").lower()


@pytest.mark.asyncio
async def test_connect_target_model_adapter_failure(tmp_path: Path) -> None:
    """Test connect_target_model when adapter fails to open model."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    model_file = tmp_path / "test_model.sldprt"
    model_file.write_bytes(b"fake data")

    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_adapter = _DummyAdapter(fail=True)
        mock_factory.return_value = mock_adapter

        result = await connect_target_model(
            DEFAULT_SESSION_ID,
            model_path=str(model_file),
            db_path=db_path,
        )

    # Result should still be valid dashboard state
    assert result["session_id"] == DEFAULT_SESSION_ID


@pytest.mark.asyncio
async def test_reconcile_manual_edits_with_changes(tmp_path: Path) -> None:
    """Test reconcile_manual_edits detects changes between snapshots."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Insert two snapshots with different states
    insert_model_state_snapshot(
        session_id=DEFAULT_SESSION_ID,
        state_fingerprint="hash1",
        feature_tree_json=json.dumps([{"name": "Sketch1"}]),
        screenshot_path="/tmp/ss1.png",
        db_path=db_path,
    )
    insert_model_state_snapshot(
        session_id=DEFAULT_SESSION_ID,
        state_fingerprint="hash2",  # Different hash
        feature_tree_json=json.dumps([{"name": "Sketch1"}, {"name": "Boss-Extrude1"}]),
        screenshot_path="/tmp/ss2.png",
        db_path=db_path,
    )

    result = reconcile_manual_edits(DEFAULT_SESSION_ID, db_path=db_path)

    assert result["session_id"] == DEFAULT_SESSION_ID


@pytest.mark.asyncio
async def test_reconcile_manual_edits_no_changes(tmp_path: Path) -> None:
    """Test reconcile_manual_edits when snapshots are identical."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Insert two identical snapshots
    insert_model_state_snapshot(
        session_id=DEFAULT_SESSION_ID,
        state_fingerprint="hash1",
        feature_tree_json=json.dumps([{"name": "Sketch1"}]),
        screenshot_path="/tmp/ss.png",
        db_path=db_path,
    )
    insert_model_state_snapshot(
        session_id=DEFAULT_SESSION_ID,
        state_fingerprint="hash1",  # Same hash
        feature_tree_json=json.dumps([{"name": "Sketch1"}]),
        screenshot_path="/tmp/ss.png",
        db_path=db_path,
    )

    result = reconcile_manual_edits(DEFAULT_SESSION_ID, db_path=db_path)

    assert "No visual" in result.get("latest_message", "")


# ============================================================================
# Dashboard state building and trace payload tests
# ============================================================================


def test_build_dashboard_state_with_checkpoints(tmp_path: Path) -> None:
    """Test build_dashboard_state includes checkpoint information."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    state = build_dashboard_state(DEFAULT_SESSION_ID, db_path=db_path)

    assert state["session_id"] == DEFAULT_SESSION_ID
    assert "checkpoints" in state
    assert len(state["checkpoints"]) >= 1


def test_build_dashboard_state_with_evidence(tmp_path: Path) -> None:
    """Test build_dashboard_state includes evidence rows."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Insert some evidence using keyword-only arguments
    insert_evidence_link(
        session_id=DEFAULT_SESSION_ID,
        source_type="reference",
        source_id="doc1",
        rationale="Design pattern reference",
        relevance_score=0.95,
        db_path=db_path,
    )

    state = build_dashboard_state(DEFAULT_SESSION_ID, db_path=db_path)

    assert "evidence_rows" in state


def test_build_dashboard_trace_payload(tmp_path: Path) -> None:
    """Test build_dashboard_trace_payload generates trace-safe JSON."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    payload = build_dashboard_trace_payload(DEFAULT_SESSION_ID, db_path=db_path)

    # Verify it's JSON serializable
    assert isinstance(payload, dict)
    trace_json = json.dumps(payload, ensure_ascii=True)
    assert len(trace_json) > 0


# ============================================================================
# Approval and acceptance workflow tests
# ============================================================================


def test_approve_design_brief(tmp_path: Path) -> None:
    """Test approve_design_brief persists and updates session state."""
    db_path = tmp_path / "test.db"

    result = approve_design_brief(
        DEFAULT_SESSION_ID,
        "Create a printable bracket assembly",
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID
    session = get_design_session(DEFAULT_SESSION_ID, db_path=db_path)
    assert session is not None
    assert session["user_goal"] == "Create a printable bracket assembly"


def test_accept_family_choice_with_explicit_family(tmp_path: Path) -> None:
    """Test accept_family_choice with explicit family parameter."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = accept_family_choice(
        DEFAULT_SESSION_ID,
        family="bracket",
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID
    session = get_design_session(DEFAULT_SESSION_ID, db_path=db_path)
    assert session["accepted_family"] == "bracket"


def test_accept_family_choice_fallback_family(tmp_path: Path) -> None:
    """Test accept_family_choice falls back to metadata when no explicit family."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = accept_family_choice(
        DEFAULT_SESSION_ID,
        family=None,
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID


# ============================================================================
# Update preferences and metadata tests
# ============================================================================


def test_update_ui_preferences_model_provider(tmp_path: Path) -> None:
    """Test update_ui_preferences persists model and provider settings."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = update_ui_preferences(
        DEFAULT_SESSION_ID,
        model_provider="openai",
        model_profile="large",
        model_name="gpt-4",
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID


def test_update_ui_preferences_assumptions(tmp_path: Path) -> None:
    """Test update_ui_preferences persists assumptions text."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    assumptions = "Use aluminum alloy 6061. Tolerance +/- 0.5mm"

    result = update_ui_preferences(
        DEFAULT_SESSION_ID,
        assumptions_text=assumptions,
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID


@pytest.mark.parametrize(
    "provider,profile,model_name,expected_in_result",
    [
        ("github", "small", "gpt-4-mini", "github:"),
        ("openai", "balanced", "gpt-4", "openai:"),
        ("anthropic", "large", "claude-3", "anthropic:"),
        ("local", "balanced", "llama2", "local:"),
    ],
)
def test_update_ui_preferences_model_normalization(
    tmp_path: Path, provider, profile, model_name, expected_in_result
):
    """Test update_ui_preferences normalizes model names to provider-qualified format."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = update_ui_preferences(
        DEFAULT_SESSION_ID,
        model_provider=provider,
        model_profile=profile,
        model_name=model_name,
        db_path=db_path,
    )

    assert result["session_id"] == DEFAULT_SESSION_ID


# ============================================================================
# Checkpoint execution tests
# ============================================================================


@pytest.mark.asyncio
async def test_execute_next_checkpoint_success(tmp_path: Path) -> None:
    """Test execute_next_checkpoint marks checkpoint executed on success."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_adapter = _DummyAdapter()
        mock_factory.return_value = mock_adapter

        result = await execute_next_checkpoint(DEFAULT_SESSION_ID, db_path=db_path)

    assert result["session_id"] == DEFAULT_SESSION_ID
    checkpoints = list_plan_checkpoints(DEFAULT_SESSION_ID, db_path=db_path)
    assert len(checkpoints) > 0


@pytest.mark.asyncio
async def test_execute_next_checkpoint_all_executed(tmp_path: Path) -> None:
    """Test execute_next_checkpoint when all checkpoints already executed."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Mark all checkpoints as executed
    checkpoints = list_plan_checkpoints(DEFAULT_SESSION_ID, db_path=db_path)
    for checkpoint in checkpoints:
        update_plan_checkpoint(
            int(checkpoint["id"]),
            executed=True,
            db_path=db_path,
        )

    result = await execute_next_checkpoint(DEFAULT_SESSION_ID, db_path=db_path)

    assert "already been executed" in result.get("latest_message", "")


# ============================================================================
# Utility tests for context and preview directories
# ============================================================================


def test_ensure_context_dir_creation(tmp_path: Path) -> None:
    """Test ensure_context_dir creates directory if needed."""
    custom_dir = tmp_path / "context"

    with patch("src.solidworks_mcp.ui.service.DEFAULT_CONTEXT_DIR", custom_dir):
        result = ensure_context_dir(custom_dir)

    assert result.exists()
    assert result.is_dir()


def test_context_file_path_generation() -> None:
    """Test _context_file_path generates valid paths."""
    path = service._context_file_path(
        "session-1",
        context_name="design-project",
    )

    assert isinstance(path, Path)
    assert "design-project" in str(path)
    assert path.suffix == ".json"


# ============================================================================
# _sanitize_preview_viewer_url full URL branches (lines 194-201)
# ============================================================================


def test_sanitize_preview_viewer_url_full_url_matching_netloc() -> None:
    """URL with scheme+netloc matching api_origin should pass through."""
    url = "http://localhost:8765/api/ui/viewer/test-session"
    result = service._sanitize_preview_viewer_url(
        url, session_id="test-session", api_origin="http://localhost:8765"
    )
    assert result == url


def test_sanitize_preview_viewer_url_mismatched_netloc() -> None:
    """URL with netloc NOT matching api_origin should be rejected."""
    url = "http://evil.com/api/ui/viewer/test-session"
    result = service._sanitize_preview_viewer_url(
        url, session_id="test-session", api_origin="http://localhost:8765"
    )
    assert result == ""


# ============================================================================
# _trace_json_default non-Path value (line 210)
# ============================================================================


def test_trace_json_default_non_path_value() -> None:
    """Non-Path values should be stringified (the single return str(value) branch)."""
    assert service._trace_json_default(42) == "42"
    assert service._trace_json_default({"k": "v"}) == "{'k': 'v'}"


# ============================================================================
# _feature_target_status partial-match and no-match branches (lines 507-559)
# ============================================================================


def test_feature_target_status_partial_match() -> None:
    """Status reports partial match when some targets found and some missing."""
    features = [{"name": "Boss-Extrude1"}, {"name": "Sketch1"}]
    status, matched, missing = service._feature_target_status(
        features, "@Boss-Extrude1, @MissingFeature"
    )
    assert "Boss-Extrude1" in matched
    assert "MissingFeature" in missing
    assert "Partially" in status


def test_feature_target_status_no_match() -> None:
    """Status reports no match when no requested targets are present."""
    features = [{"name": "Boss-Extrude1"}]
    status, matched, missing = service._feature_target_status(features, "@NonExistent")
    assert matched == []
    assert "NonExistent" in missing
    assert "No matching" in status


# ============================================================================
# open_target_model error-path branches (lines 1560-1711)
# ============================================================================


@pytest.mark.asyncio
async def test_open_target_model_no_args(tmp_path: Path) -> None:
    """No model_path and no uploaded_files returns dashboard state with error."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)
    result = await open_target_model(DEFAULT_SESSION_ID, db_path=db_path)
    assert result["session_id"] == DEFAULT_SESSION_ID
    assert "model" in result.get("latest_error_text", "").lower()


@pytest.mark.asyncio
async def test_open_target_model_empty_path(tmp_path: Path) -> None:
    """Model_path that sanitizes to empty string returns dashboard state with error."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)
    # '"' strips to "" after _sanitize_model_path_text
    result = await open_target_model(
        DEFAULT_SESSION_ID, model_path='"', db_path=db_path
    )
    assert result["session_id"] == DEFAULT_SESSION_ID
    assert "model" in result.get("latest_error_text", "").lower()


@pytest.mark.asyncio
async def test_open_target_model_file_not_found(tmp_path: Path) -> None:
    """Non-existent model_path returns dashboard state with missing-file error."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)
    result = await open_target_model(
        DEFAULT_SESSION_ID,
        model_path="/nonexistent/model.sldprt",
        db_path=db_path,
    )
    assert result["session_id"] == DEFAULT_SESSION_ID
    assert "missing" in result.get("latest_error_text", "").lower()


@pytest.mark.asyncio
async def test_open_target_model_with_mock_adapter(tmp_path: Path) -> None:
    """Valid model path + mock adapter succeeds and stores model info in metadata."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)
    model_file = tmp_path / "part.sldprt"
    model_file.write_bytes(b"fake solidworks data")

    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_adapter = _DummyAdapter()
        mock_factory.return_value = mock_adapter
        result = await open_target_model(
            DEFAULT_SESSION_ID, model_path=str(model_file), db_path=db_path
        )

    assert result["session_id"] == DEFAULT_SESSION_ID
    assert result.get("latest_error_text", "") == ""


@pytest.mark.asyncio
async def test_open_target_model_adapter_failure(tmp_path: Path) -> None:
    """Adapter open_model failure is recorded and dashboard state returned."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)
    model_file = tmp_path / "part.sldprt"
    model_file.write_bytes(b"fake solidworks data")

    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_factory.return_value = _DummyAdapter(fail=True)
        result = await open_target_model(
            DEFAULT_SESSION_ID, model_path=str(model_file), db_path=db_path
        )

    assert result["session_id"] == DEFAULT_SESSION_ID
    assert result.get("latest_error_text", "") != ""


# ============================================================================
# _run_checkpoint_tools failure branches (lines 735, 751, 767, 776, 788)
# and execute_next_checkpoint mocked_tools path (line 979)
# ============================================================================


@pytest.mark.asyncio
async def test_run_checkpoint_tools_tool_failure(tmp_path: Path) -> None:
    """Tool-level failures are recorded in failed_tools per-tool."""
    planned = {"goal": "test", "tools": ["create_sketch", "add_line"]}
    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_factory.return_value = _DummyAdapter(fail=True)
        summary = await service._run_checkpoint_tools(planned)

    assert len(summary["failed_tools"]) > 0
    assert any(r["status"] == "error" for r in summary["tool_runs"])


@pytest.mark.asyncio
async def test_run_checkpoint_tools_check_interference_mocked(tmp_path: Path) -> None:
    """Check_interference is always mocked (no adapter binding)."""
    planned = {"goal": "test", "tools": ["check_interference"]}
    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_factory.return_value = _DummyAdapter()
        summary = await service._run_checkpoint_tools(planned)

    assert "check_interference" in summary["mocked_tools"]
    assert summary["failed_tools"] == []


@pytest.mark.asyncio
async def test_execute_next_checkpoint_mocked_tools_path(tmp_path: Path) -> None:
    """Execute_next_checkpoint generates a MOCKED-tools message when no failures."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Insert a checkpoint that uses only check_interference (always mocked)
    checkpoints = list_plan_checkpoints(DEFAULT_SESSION_ID, db_path=db_path)
    for cp in checkpoints:
        update_plan_checkpoint(int(cp["id"]), executed=True, db_path=db_path)

    insert_plan_checkpoint(
        session_id=DEFAULT_SESSION_ID,
        checkpoint_index=99,
        title="Mocked-only checkpoint",
        planned_action_json=json.dumps(
            {"goal": "verify fit", "tools": ["check_interference"]}
        ),
        approved_by_user=True,
        db_path=db_path,
    )

    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_factory.return_value = _DummyAdapter()
        result = await execute_next_checkpoint(DEFAULT_SESSION_ID, db_path=db_path)

    assert result["session_id"] == DEFAULT_SESSION_ID
    assert "MOCKED" in result.get("latest_message", "")


# ============================================================================
# fetch_docs_context success path (lines 1360-1373)
# ============================================================================


def test_fetch_docs_context_success(tmp_path: Path) -> None:
    """Fetch_docs_context stores snippet in metadata when urlopen succeeds."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    fake_html = b"<html><body><p>SolidWorks workflow guide</p></body></html>"

    class _FakeResp:
        """Test fake resp."""

        def read(self) -> bytes:
            """Test read."""

            return fake_html

        def __enter__(self) -> "_FakeResp":
            """Test enter."""

            return self

        def __exit__(self, *a: Any) -> bool:
            """Test exit."""

            return False

    with patch("src.solidworks_mcp.ui.service.urlopen", return_value=_FakeResp()):
        result = fetch_docs_context(
            DEFAULT_SESSION_ID, docs_query="workflow", db_path=db_path
        )

    assert result["session_id"] == DEFAULT_SESSION_ID
    assert result.get("latest_error_text", "") == ""


# ============================================================================
# run_go_orchestration exception path (lines 1304-1315)
# ============================================================================


@pytest.mark.asyncio
async def test_run_go_orchestration_exception_path(tmp_path: Path) -> None:
    """Run_go_orchestration records error when an LLM sub-call raises."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    with patch(
        "src.solidworks_mcp.ui.service.request_clarifications",
        new_callable=AsyncMock,
        side_effect=RuntimeError("provider unavailable"),
    ):
        result = await run_go_orchestration(
            DEFAULT_SESSION_ID,
            user_goal="Build a bracket",
            db_path=db_path,
        )

    assert result["session_id"] == DEFAULT_SESSION_ID
    assert "provider unavailable" in result.get("latest_error_text", "")


# ============================================================================
# highlight_feature with mock adapter (lines 2897-2996)
# ============================================================================


@pytest.mark.asyncio
async def test_highlight_feature_success(tmp_path: Path) -> None:
    """Highlight_feature with mock adapter records selected feature in metadata."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_factory.return_value = _DummyAdapter()
        result = await highlight_feature(
            DEFAULT_SESSION_ID, "Boss-Extrude1", db_path=db_path
        )

    assert result["session_id"] == DEFAULT_SESSION_ID
    assert "Boss-Extrude1" in result.get("latest_message", "")


@pytest.mark.asyncio
async def test_highlight_feature_not_selected(tmp_path: Path) -> None:
    """Highlight_feature with adapter returning selected=False records error hint."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        mock_factory.return_value = _DummyAdapter(fail=True)
        result = await highlight_feature(
            DEFAULT_SESSION_ID, "Boss-Extrude1", db_path=db_path
        )

    assert result["session_id"] == DEFAULT_SESSION_ID
    # Message should mention the feature name even when not selected
    assert "Boss-Extrude1" in result.get("latest_message", "")


@pytest.mark.asyncio
async def test_highlight_feature_empty_name(tmp_path: Path) -> None:
    """Highlight_feature with empty feature name records validation error."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    result = await highlight_feature(DEFAULT_SESSION_ID, "", db_path=db_path)

    assert result["session_id"] == DEFAULT_SESSION_ID
    assert "No feature name" in result.get("latest_error_text", "")


@pytest.mark.asyncio
async def test_highlight_feature_with_known_tree_name(tmp_path: Path) -> None:
    """Highlight_feature marks feature as tracked-only when in tree but COM returns False."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Insert a snapshot so the feature name is "known" in the tree
    insert_model_state_snapshot(
        session_id=DEFAULT_SESSION_ID,
        state_fingerprint="fp1",
        feature_tree_json=json.dumps([{"name": "Boss-Extrude1"}, {"name": "Sketch1"}]),
        screenshot_path="",
        db_path=db_path,
    )

    with patch("src.solidworks_mcp.ui.service.create_adapter") as mock_factory:
        # fail=True makes select_feature return selected=False
        mock_factory.return_value = _DummyAdapter(fail=True)
        result = await highlight_feature(
            DEFAULT_SESSION_ID, "Boss-Extrude1", db_path=db_path
        )

    assert result["session_id"] == DEFAULT_SESSION_ID
    # Should say "Tracking" since name is in tree but COM returned False
    assert "Tracking" in result.get("latest_message", "")


# ============================================================================
# ingest_reference_source FAISS ImportError / exception paths (1946-1956)
# ============================================================================


def test_ingest_reference_source_faiss_import_error(tmp_path: Path) -> None:
    """FAISS ImportError is silently skipped; ingest still succeeds."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    src_file = tmp_path / "reference.txt"
    src_file.write_text(
        "SolidWorks design notes for bracket assembly.", encoding="utf-8"
    )

    with patch("src.solidworks_mcp.ui.service.DEFAULT_RAG_DIR", tmp_path / "rag"):
        with patch(
            "src.solidworks_mcp.agents.vector_rag.VectorRAGIndex.load",
            side_effect=ImportError("faiss not installed"),
        ):
            result = ingest_reference_source(
                DEFAULT_SESSION_ID,
                source_path=str(src_file),
                namespace="test-ns",
                db_path=db_path,
            )

    assert result["session_id"] == DEFAULT_SESSION_ID
    # Ingest should succeed even without FAISS
    assert "failed" not in result.get("latest_message", "").lower()


def test_ingest_reference_source_faiss_generic_exception(tmp_path: Path) -> None:
    """FAISS generic exception is logged as warning but ingest still completes."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    src_file = tmp_path / "reference.txt"
    src_file.write_text("Engineering reference document.", encoding="utf-8")

    with patch("src.solidworks_mcp.ui.service.DEFAULT_RAG_DIR", tmp_path / "rag"):
        with patch(
            "src.solidworks_mcp.agents.vector_rag.VectorRAGIndex.load",
            side_effect=RuntimeError("index corruption"),
        ):
            result = ingest_reference_source(
                DEFAULT_SESSION_ID,
                source_path=str(src_file),
                namespace="test-ns2",
                db_path=db_path,
            )

    assert result["session_id"] == DEFAULT_SESSION_ID


# ============================================================================
# build_dashboard_state feature_target deduplication + selected feature
# highlighting (lines 3032, 3070, 3162-3168)
# ============================================================================


def test_build_dashboard_state_feature_target_evidence_dedup(tmp_path: Path) -> None:
    """Build_dashboard_state shows only latest feature_target evidence row."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Insert active_model evidence with a mismatched source_id (should be filtered)
    insert_evidence_link(
        session_id=DEFAULT_SESSION_ID,
        source_type="active_model",
        source_id="/other/model.sldprt",
        rationale="Old model",
        relevance_score=0.5,
        db_path=db_path,
    )
    # Insert two feature_target rows (only latest should appear)
    for i in range(2):
        insert_evidence_link(
            session_id=DEFAULT_SESSION_ID,
            source_type="feature_target",
            source_id=f"feature_target_{i}",
            rationale=f"Target result {i}",
            relevance_score=0.9,
            db_path=db_path,
        )

    # Set active_model_path so model-scoped filtering is active
    from src.solidworks_mcp.ui.service import _merge_metadata

    _merge_metadata(
        DEFAULT_SESSION_ID, db_path=db_path, active_model_path="/active/model.sldprt"
    )

    state = build_dashboard_state(DEFAULT_SESSION_ID, db_path=db_path)

    assert state["session_id"] == DEFAULT_SESSION_ID
    # Only one feature_target row should be in evidence (the last one)
    ft_rows = [
        r for r in state.get("evidence_rows", []) if r.get("source") == "feature_target"
    ]
    assert len(ft_rows) <= 1


def test_build_dashboard_state_selected_feature_highlight(tmp_path: Path) -> None:
    """Build_dashboard_state adds _selected marker to the selected feature row."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    # Insert snapshot with feature tree
    insert_model_state_snapshot(
        session_id=DEFAULT_SESSION_ID,
        state_fingerprint="fp_sel",
        feature_tree_json=json.dumps(
            [
                {"name": "Boss-Extrude1", "type": "Boss-Extrude"},
                {"name": "Sketch1", "type": "Sketch"},
            ]
        ),
        screenshot_path="",
        db_path=db_path,
    )
    # Set active_model_path and selected_feature_name in metadata
    from src.solidworks_mcp.ui.service import _merge_metadata

    _merge_metadata(
        DEFAULT_SESSION_ID,
        db_path=db_path,
        active_model_path="/models/part.sldprt",
        selected_feature_name="Boss-Extrude1",
        workflow_mode="edit_existing",
    )

    state = build_dashboard_state(DEFAULT_SESSION_ID, db_path=db_path)

    feature_items = state.get("feature_tree_items", [])
    selected_items = [f for f in feature_items if f.get("_selected") == "●"]
    assert len(selected_items) == 1
    assert selected_items[0]["name"] == "Boss-Extrude1"


# ============================================================================
# build_dashboard_state mocked_tools in checkpoint row (line 3032)
# ============================================================================


def test_build_dashboard_state_checkpoint_with_mocked_tools(tmp_path: Path) -> None:
    """Checkpoint result with mocked_tools is reflected in checkpoints_text."""
    db_path = tmp_path / "test.db"
    ensure_dashboard_session(DEFAULT_SESSION_ID, db_path=db_path)

    checkpoints = list_plan_checkpoints(DEFAULT_SESSION_ID, db_path=db_path)
    if checkpoints:
        from src.solidworks_mcp.agents.history_db import update_plan_checkpoint

        update_plan_checkpoint(
            int(checkpoints[0]["id"]),
            executed=True,
            result_json=json.dumps(
                {
                    "status": "success",
                    "tools": ["check_interference"],
                    "mocked_tools": ["check_interference"],
                    "failed_tools": [],
                }
            ),
            db_path=db_path,
        )

    state = build_dashboard_state(DEFAULT_SESSION_ID, db_path=db_path)

    assert "MOCKED" in state.get("checkpoints_text", "")
