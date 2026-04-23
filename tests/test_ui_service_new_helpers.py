"""Coverage tests for new helper and service functions added to service.py.

Targets the following previously-uncovered code paths:
- ensure_context_dir
- _safe_context_name
- _context_file_path
- _filter_docs_text
- _normalize_model_name_for_provider
- _default_model_for_profile
- _feature_grounding_warning_text
- update_session_notes
- save_session_context
- load_session_context (success, file-not-found, corrupt-json branches)
- fetch_docs_context (network error path)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.solidworks_mcp.ui import service
from src.solidworks_mcp.ui.service import (
    _context_file_path,
    _default_model_for_profile,
    _feature_grounding_warning_text,
    _filter_docs_text,
    _normalize_model_name_for_provider,
    _safe_context_name,
    ensure_context_dir,
    fetch_docs_context,
    load_session_context,
    save_session_context,
    update_session_notes,
)


# ---------------------------------------------------------------------------
# ensure_context_dir
# ---------------------------------------------------------------------------


def test_ensure_context_dir_creates_dir(tmp_path: Path) -> None:
    target = tmp_path / "ctx_dir"
    result = ensure_context_dir(target)
    assert result == target
    assert target.is_dir()


def test_ensure_context_dir_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "DEFAULT_CONTEXT_DIR", tmp_path / "default_ctx")
    result = ensure_context_dir()
    assert result.is_dir()


# ---------------------------------------------------------------------------
# _safe_context_name
# ---------------------------------------------------------------------------


def test_safe_context_name_alphanumeric() -> None:
    assert _safe_context_name("my-session_1", "sid") == "my-session_1"


def test_safe_context_name_replaces_special_chars() -> None:
    result = _safe_context_name("my session/name", "sid")
    assert "/" not in result
    assert " " not in result


def test_safe_context_name_falls_back_to_session_id() -> None:
    result = _safe_context_name(None, "abc123")
    assert result == "abc123"


def test_safe_context_name_empty_falls_back_to_default() -> None:
    result = _safe_context_name("", "")
    assert result == "prefab-dashboard"


def test_safe_context_name_strips_leading_trailing_hyphens() -> None:
    result = _safe_context_name("---name---", "sid")
    assert not result.startswith("-")
    assert not result.endswith("-")


# ---------------------------------------------------------------------------
# _context_file_path
# ---------------------------------------------------------------------------


def test_context_file_path_creates_path(tmp_path: Path) -> None:
    p = _context_file_path("sess1", context_name="myctx", context_dir=tmp_path)
    assert p.name == "myctx.json"
    assert p.parent == tmp_path


def test_context_file_path_uses_session_id_when_no_name(tmp_path: Path) -> None:
    p = _context_file_path("sess-abc", context_dir=tmp_path)
    assert p.name == "sess-abc.json"


# ---------------------------------------------------------------------------
# _filter_docs_text
# ---------------------------------------------------------------------------


def test_filter_docs_text_empty_returns_placeholder() -> None:
    result = _filter_docs_text("", "solidworks")
    assert "No docs content" in result


def test_filter_docs_text_whitespace_only_returns_placeholder() -> None:
    result = _filter_docs_text("   \n  \n  ", "solidworks")
    assert "No docs content" in result


def test_filter_docs_text_filters_by_query() -> None:
    raw = "SolidWorks sketch help\nPython tutorial\nsolidworks extrude guide"
    result = _filter_docs_text(raw, "solidworks")
    assert "solidworks" in result.lower()
    # Python tutorial is unrelated and may be filtered
    assert "SolidWorks" in result or "solidworks" in result


def test_filter_docs_text_no_query_returns_first_lines() -> None:
    raw = "\n".join(f"Line {i}" for i in range(60))
    result = _filter_docs_text(raw, "")
    assert "Line 0" in result


def test_filter_docs_text_respects_max_chars() -> None:
    raw = "solidworks " * 500
    result = _filter_docs_text(raw, "solidworks", max_chars=100)
    assert len(result) <= 100


def test_filter_docs_text_falls_back_when_no_ranked_lines() -> None:
    raw = "Python tutorial\nJava guide\nRust reference"
    result = _filter_docs_text(raw, "solidworks")
    # No lines match "solidworks" so falls back to all lines[:40]
    assert "Python" in result or "Java" in result or "Rust" in result


# ---------------------------------------------------------------------------
# _normalize_model_name_for_provider
# ---------------------------------------------------------------------------


def test_normalize_model_name_empty_returns_default() -> None:
    result = _normalize_model_name_for_provider(
        None, provider="github", profile="balanced"
    )
    assert result.startswith("github:")


def test_normalize_model_name_already_qualified() -> None:
    result = _normalize_model_name_for_provider("openai:gpt-4", provider="github")
    assert result == "openai:gpt-4"


def test_normalize_model_name_local_provider() -> None:
    result = _normalize_model_name_for_provider("gemma4-e4b", provider="local")
    assert result == "local:gemma4-e4b"


def test_normalize_model_name_github_with_slash() -> None:
    result = _normalize_model_name_for_provider("openai/gpt-4.1", provider="github")
    assert result == "github:openai/gpt-4.1"


def test_normalize_model_name_github_without_slash() -> None:
    result = _normalize_model_name_for_provider("gpt-4.1-mini", provider="github")
    assert result == "github:openai/gpt-4.1-mini"


def test_normalize_model_name_openai_provider() -> None:
    result = _normalize_model_name_for_provider("gpt-4", provider="openai")
    assert result == "openai:gpt-4"


def test_normalize_model_name_anthropic_provider() -> None:
    result = _normalize_model_name_for_provider("claude-3", provider="anthropic")
    assert result == "anthropic:claude-3"


def test_normalize_model_name_custom_provider() -> None:
    result = _normalize_model_name_for_provider("some-model", provider="custom")
    assert result == "some-model"


# ---------------------------------------------------------------------------
# _default_model_for_profile
# ---------------------------------------------------------------------------


def test_default_model_local_small() -> None:
    assert "e2b" in _default_model_for_profile("local", "small")


def test_default_model_local_balanced() -> None:
    assert "e4b" in _default_model_for_profile("local", "balanced")


def test_default_model_local_large() -> None:
    assert "26b" in _default_model_for_profile("local", "large")


def test_default_model_local_unknown_profile() -> None:
    # Unknown profile falls back to balanced
    assert "e4b" in _default_model_for_profile("local", "unknown-tier")


def test_default_model_github_small() -> None:
    result = _default_model_for_profile("github", "small")
    assert "mini" in result.lower()


def test_default_model_github_unknown_profile() -> None:
    result = _default_model_for_profile("github", "ultra")
    assert result.startswith("github:")


# ---------------------------------------------------------------------------
# _feature_grounding_warning_text
# ---------------------------------------------------------------------------


def test_feature_grounding_no_model_path_returns_empty() -> None:
    result = _feature_grounding_warning_text(
        active_model_path="",
        feature_target_text="Boss-Extrude1",
        feature_tree_count=0,
    )
    assert result == ""


def test_feature_grounding_no_feature_target_returns_empty() -> None:
    result = _feature_grounding_warning_text(
        active_model_path="/some/model.sldprt",
        feature_target_text="",
        feature_tree_count=0,
    )
    assert result == ""


def test_feature_grounding_has_tree_returns_empty() -> None:
    result = _feature_grounding_warning_text(
        active_model_path="/some/model.sldprt",
        feature_target_text="Boss-Extrude1",
        feature_tree_count=5,
    )
    assert result == ""


def test_feature_grounding_warning_emitted() -> None:
    result = _feature_grounding_warning_text(
        active_model_path="/some/model.sldprt",
        feature_target_text="Boss-Extrude1",
        feature_tree_count=0,
    )
    assert "Grounding is unavailable" in result
    assert "feature tree" in result.lower()


# ---------------------------------------------------------------------------
# update_session_notes
# ---------------------------------------------------------------------------


def test_update_session_notes_persists(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    state = update_session_notes(
        "sess-notes",
        notes_text="My engineering notes here.",
        db_path=db,
        api_origin="http://testserver",
    )
    assert isinstance(state, dict)
    # Notes text should be in the metadata
    meta = json.loads(
        service.get_design_session("sess-notes", db_path=db).get("metadata_json", "{}")
    )
    assert meta.get("notes_text") == "My engineering notes here."


# ---------------------------------------------------------------------------
# save_session_context
# ---------------------------------------------------------------------------


def test_save_session_context_writes_file(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    ctx_dir = tmp_path / "ctx"
    state = save_session_context(
        "sess-save",
        context_name="my-snapshot",
        db_path=db,
        context_dir=ctx_dir,
        api_origin="http://testserver",
    )
    assert isinstance(state, dict)
    ctx_file = ctx_dir / "my-snapshot.json"
    assert ctx_file.exists()
    payload = json.loads(ctx_file.read_text(encoding="utf-8"))
    assert payload["session_id"] == "sess-save"
    assert "state" in payload
    assert "saved_at" in payload


# ---------------------------------------------------------------------------
# load_session_context
# ---------------------------------------------------------------------------


def test_load_session_context_file_not_found(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    ctx_dir = tmp_path / "ctx"
    state = load_session_context(
        "sess-load",
        context_file=str(ctx_dir / "nonexistent.json"),
        db_path=db,
        api_origin="http://testserver",
    )
    assert isinstance(state, dict)
    meta = json.loads(
        service.get_design_session("sess-load", db_path=db).get("metadata_json", "{}")
    )
    assert "not found" in (meta.get("context_load_status") or "").lower()


def test_load_session_context_corrupt_json(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    ctx_dir = tmp_path / "ctx"
    ctx_dir.mkdir(parents=True)
    bad_file = ctx_dir / "bad.json"
    bad_file.write_text("NOT JSON {{{", encoding="utf-8")
    state = load_session_context(
        "sess-corrupt",
        context_file=str(bad_file),
        db_path=db,
        api_origin="http://testserver",
    )
    assert isinstance(state, dict)
    meta = json.loads(
        service.get_design_session("sess-corrupt", db_path=db).get(
            "metadata_json", "{}"
        )
    )
    assert "failed" in (meta.get("context_load_status") or "").lower()


def test_load_session_context_success(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    ctx_dir = tmp_path / "ctx"
    # First save, then load
    save_session_context(
        "sess-roundtrip",
        context_name="roundtrip",
        db_path=db,
        context_dir=ctx_dir,
        api_origin="http://testserver",
    )
    state = load_session_context(
        "sess-roundtrip",
        context_file=str(ctx_dir / "roundtrip.json"),
        db_path=db,
        api_origin="http://testserver",
    )
    assert isinstance(state, dict)
    meta = json.loads(
        service.get_design_session("sess-roundtrip", db_path=db).get(
            "metadata_json", "{}"
        )
    )
    assert "loaded" in (meta.get("context_load_status") or "").lower()


# ---------------------------------------------------------------------------
# fetch_docs_context — network error branch
# ---------------------------------------------------------------------------


def test_fetch_docs_context_network_error(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    with patch(
        "src.solidworks_mcp.ui.service.urlopen",
        side_effect=OSError("connection refused"),
    ):
        state = fetch_docs_context(
            "sess-docs-err",
            docs_query="solidworks sketch",
            db_path=db,
            api_origin="http://testserver",
        )
    assert isinstance(state, dict)
    meta = json.loads(
        service.get_design_session("sess-docs-err", db_path=db).get(
            "metadata_json", "{}"
        )
    )
    assert meta.get("latest_error_text") or meta.get("docs_context_text") == ""
