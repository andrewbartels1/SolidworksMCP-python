"""Tests for solidworks_mcp.utils.feature_tree_classifier."""

from __future__ import annotations

import pytest

from solidworks_mcp.utils.feature_tree_classifier import (
    classify_feature_tree_snapshot,
    _as_lower_text,
    _feature_text,
    _has_any,
    _match_examples,
)


# ---------------------------------------------------------------------------
# Low-level helper tests
# ---------------------------------------------------------------------------


def test_as_lower_text_handles_none_and_whitespace() -> None:
    assert _as_lower_text(None) == ""
    assert _as_lower_text("  Hello World  ") == "hello world"
    assert _as_lower_text(42) == "42"


def test_feature_text_combines_name_and_type() -> None:
    feature = {"name": "Boss-Extrude1", "type": "BossExtrude"}
    result = _feature_text(feature)
    assert "boss-extrude1" in result
    assert "bossextrude" in result


def test_feature_text_handles_missing_keys() -> None:
    result = _feature_text({})
    assert result == ""


def test_has_any_returns_true_on_match() -> None:
    texts = ["sheet-metal feature", "normal part"]
    assert _has_any(texts, ("sheet-metal",)) is True
    assert _has_any(texts, ("loft",)) is False


def test_match_examples_respects_limit() -> None:
    texts = ["loft1", "loft2", "loft3", "loft4", "loft5"]
    results = _match_examples(texts, ("loft",), limit=3)
    assert len(results) == 3
    assert all("loft" in r for r in results)


def test_match_examples_returns_empty_when_no_match() -> None:
    results = _match_examples(["extrude1", "sketch2"], ("revolve",))
    assert results == []


# ---------------------------------------------------------------------------
# classify_feature_tree_snapshot — all branches
# ---------------------------------------------------------------------------


def test_classify_assembly_by_document_type() -> None:
    result = classify_feature_tree_snapshot({"type": "assembly"}, [])
    assert result["family"] == "assembly"
    assert result["confidence"] == "high"
    assert result["recommended_workflow"] == "assembly-planning"
    assert result["needs_vba"] is False


def test_classify_assembly_by_feature_tokens() -> None:
    features = [{"name": "mate1", "type": ""}]
    result = classify_feature_tree_snapshot({"type": "part"}, features)
    assert result["family"] == "assembly"
    assert result["confidence"] == "medium"


def test_classify_drawing_by_document_type() -> None:
    result = classify_feature_tree_snapshot({"type": "drawing"}, [])
    assert result["family"] == "drawing"
    assert result["confidence"] == "high"
    assert result["recommended_workflow"] == "drawing-review"


def test_classify_drawing_by_feature_tokens() -> None:
    features = [{"name": "drawing view 1", "type": ""}]
    result = classify_feature_tree_snapshot({"type": "part"}, features)
    assert result["family"] == "drawing"
    assert result["confidence"] == "medium"


def test_classify_sheet_metal() -> None:
    features = [{"name": "Base-Flange1", "type": "sheet-metal"}]
    result = classify_feature_tree_snapshot({}, features)
    assert result["family"] == "sheet_metal"
    assert result["needs_vba"] is True
    assert result["confidence"] == "high"
    assert "vba-sheet-metal" in result["recommended_workflow"]
    assert len(result["next_actions"]) > 0


def test_classify_advanced_solid() -> None:
    features = [{"name": "Loft1", "type": "loft"}]
    result = classify_feature_tree_snapshot({}, features)
    assert result["family"] == "advanced_solid"
    assert result["needs_vba"] is True
    assert result["confidence"] == "medium"
    assert "vba-advanced-solid" in result["recommended_workflow"]


def test_classify_revolve() -> None:
    features = [{"name": "Boss-Revolve1", "type": "revolve"}]
    result = classify_feature_tree_snapshot({}, features)
    assert result["family"] == "revolve"
    assert result["confidence"] == "high"
    assert "direct-mcp-revolve" in result["recommended_workflow"]
    assert result["needs_vba"] is False


def test_classify_extrude() -> None:
    features = [{"name": "Boss-Extrude1", "type": "extrude"}]
    result = classify_feature_tree_snapshot({}, features)
    assert result["family"] == "extrude"
    assert result["confidence"] == "high"
    assert "direct-mcp-extrude" in result["recommended_workflow"]
    assert result["needs_vba"] is False


def test_classify_sketch_only() -> None:
    """All features are sketch-like → sketch_only family."""
    features = [
        {"name": "Sketch1", "type": "profilefeature"},
        {"name": "Sketch2", "type": "sketch"},
    ]
    result = classify_feature_tree_snapshot({}, features)
    assert result["family"] == "sketch_only"
    assert result["confidence"] == "low"
    assert len(result["warnings"]) > 0
    assert len(result["next_actions"]) >= 2


def test_classify_unknown_no_evidence() -> None:
    """Features with reference planes only → no strong family evidence → unknown."""
    features = [
        {"name": "Front Plane", "type": "refplane"},
        {"name": "Origin", "type": "originprofilefeature"},
    ]
    result = classify_feature_tree_snapshot({}, features)
    assert result["family"] == "unknown"
    assert "provisional" in result["warnings"][0]


def test_classify_handles_none_inputs() -> None:
    result = classify_feature_tree_snapshot(None, None)
    assert result["family"] == "unknown"
    assert result["document_type"] == "unknown"
    assert result["feature_count"] == 0


def test_classify_feature_count_correct() -> None:
    features = [{"name": f"f{i}", "type": "extrude"} for i in range(5)]
    result = classify_feature_tree_snapshot({}, features)
    assert result["feature_count"] == 5


def test_classify_sheet_metal_evidence_uses_fallback_when_no_match() -> None:
    """When _match_examples returns empty, the fallback string is used."""
    # Use a feature whose text contains 'hem' only in name but not type,
    # ensuring _match_examples finds it via text scan.
    features = [{"name": "hem1", "type": ""}]
    result = classify_feature_tree_snapshot({}, features)
    assert result["family"] == "sheet_metal"
    assert len(result["evidence"]) > 0


def test_classify_mixed_sketch_and_reference_not_sketch_only() -> None:
    """Mixed sketch + non-reference features → not sketch_only, falls through to unknown."""
    features = [
        {"name": "Sketch1", "type": "profilefeature"},
        {"name": "Something", "type": "someothertype"},
    ]
    result = classify_feature_tree_snapshot({}, features)
    # non_reference_count == 2 but sketch_like_count == 1, so != → unknown
    assert result["family"] == "unknown"
