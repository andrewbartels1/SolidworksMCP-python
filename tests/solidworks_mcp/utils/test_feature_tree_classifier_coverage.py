"""Tests for test utils feature tree classifier coverage."""

from src.solidworks_mcp.utils.feature_tree_classifier import (
    classify_feature_tree_snapshot,
)


def test_classify_assembly_from_feature_tokens() -> None:
    """Test classify assembly from feature tokens."""

    result = classify_feature_tree_snapshot(
        {"type": "Part"},
        [
            {"name": "Coincident Mate1", "type": "Mate", "suppressed": False},
            {"name": "Component1", "type": "Component", "suppressed": False},
        ],
    )

    assert result["family"] == "assembly"
    assert result["recommended_workflow"] == "assembly-planning"
    assert result["confidence"] == "medium"


def test_classify_drawing_from_document_type() -> None:
    """Test classify drawing from document type."""

    result = classify_feature_tree_snapshot(
        {"type": "Drawing"},
        [{"name": "Random", "type": "Unknown", "suppressed": False}],
    )

    assert result["family"] == "drawing"
    assert result["recommended_workflow"] == "drawing-review"
    assert result["confidence"] == "high"


def test_classify_advanced_solid_path() -> None:
    """Test classify advanced solid path."""

    result = classify_feature_tree_snapshot(
        {"type": "Part"},
        [{"name": "BoundaryBoss1", "type": "Boundary", "suppressed": False}],
    )

    assert result["family"] == "advanced_solid"
    assert result["needs_vba"] is True
    assert result["recommended_workflow"] == "vba-advanced-solid"


def test_classify_extrude_path() -> None:
    """Test classify extrude path."""

    result = classify_feature_tree_snapshot(
        {"type": "Part"},
        [{"name": "Boss-Extrude1", "type": "Boss-Extrude", "suppressed": False}],
    )

    assert result["family"] == "extrude"
    assert result["recommended_workflow"] == "direct-mcp-extrude"


def test_classify_unknown_path_with_non_sketch_features() -> None:
    """Test classify unknown path with non sketch features."""

    result = classify_feature_tree_snapshot(
        {"type": "Part"},
        [
            {"name": "Top Plane", "type": "RefPlane", "suppressed": False},
            {"name": "MysteryFeature", "type": "ImportedBody", "suppressed": False},
        ],
    )

    assert result["family"] == "unknown"
    assert result["warnings"]
    assert "No strong feature-family evidence" in result["warnings"][0]
