"""Tests for solidworks_mcp.utils.feature_tree_classifier."""

from __future__ import annotations

from solidworks_mcp.utils.feature_tree_classifier import (
    _as_lower_text,
    _feature_text,
    _has_any,
    _match_examples,
    build_component_tree,
    classify_feature_tree_snapshot,
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


# ---------------------------------------------------------------------------
# build_component_tree
# ---------------------------------------------------------------------------


def test_build_component_tree_handles_none_and_empty() -> None:
    assert build_component_tree(None) == {"features": [], "components": {}}
    assert build_component_tree([]) == {"features": [], "components": {}}


def test_build_component_tree_part_only_has_no_components() -> None:
    """A Part's flat list (no component tags at all) becomes root features only."""
    features = [
        {"name": "Boss-Extrude1", "type": "Boss", "component": None},
        {"name": "Sketch1", "type": "ProfileFeature", "component": None},
    ]
    tree = build_component_tree(features)
    assert len(tree["features"]) == 2
    assert tree["components"] == {}


def test_build_component_tree_flat_top_level_components() -> None:
    """Two top-level components (component_parent=None) become sibling nodes."""
    features = [
        {"name": "Mates", "type": "MateGroup", "component": None, "component_path": None},
        {
            "name": "Boss1",
            "type": "Boss",
            "component": "PartA",
            "component_path": "C:/PartA.sldprt",
            "component_parent": None,
        },
        {
            "name": "Cut1",
            "type": "Cut",
            "component": "PartB",
            "component_path": "C:/PartB.sldprt",
            "component_parent": None,
        },
    ]
    tree = build_component_tree(features)
    assert len(tree["features"]) == 1
    assert set(tree["components"].keys()) == {"PartA", "PartB"}
    assert tree["components"]["PartA"]["path"] == "C:/PartA.sldprt"
    assert [f["name"] for f in tree["components"]["PartA"]["features"]] == ["Boss1"]
    assert tree["components"]["PartA"]["components"] == {}


def test_build_component_tree_nests_subassembly_components() -> None:
    """A component whose component_parent points at another component nests under it."""
    features = [
        {
            "name": "Mate1",
            "type": "Mate",
            "component": "SubAssem-1",
            "component_path": "C:/SubAssem.sldasm",
            "component_parent": None,
        },
        {
            "name": "Boss1",
            "type": "Boss",
            "component": "PartC",
            "component_path": "C:/PartC.sldprt",
            "component_parent": "SubAssem-1",
        },
    ]
    tree = build_component_tree(features)
    assert set(tree["components"].keys()) == {"SubAssem-1"}
    sub = tree["components"]["SubAssem-1"]
    assert [f["name"] for f in sub["features"]] == ["Mate1"]
    assert set(sub["components"].keys()) == {"PartC"}
    assert [f["name"] for f in sub["components"]["PartC"]["features"]] == ["Boss1"]


def test_build_component_tree_preserves_parent_across_mixed_rows() -> None:
    """A component's first-discovered non-None parent survives later rows
    for the same component that lack component_parent or carry it as None.
    """
    features = [
        {
            "name": "Mate1",
            "type": "Mate",
            "component": "SubAssem-1",
            "component_path": "C:/SubAssem.sldasm",
            "component_parent": None,
        },
        {
            "name": "Boss1",
            "type": "Boss",
            "component": "PartC",
            "component_path": "C:/PartC.sldprt",
            "component_parent": "SubAssem-1",
        },
        {
            "name": "Fillet1",
            "type": "Fillet",
            "component": "PartC",
            "component_path": "C:/PartC.sldprt",
            "component_parent": None,
        },
        {
            "name": "Cut1",
            "type": "Cut",
            "component": "PartC",
            "component_path": "C:/PartC.sldprt",
        },
    ]
    tree = build_component_tree(features)
    assert "PartC" not in tree["components"]
    assert set(tree["components"].keys()) == {"SubAssem-1"}
    nested = tree["components"]["SubAssem-1"]["components"]
    assert set(nested.keys()) == {"PartC"}
    assert [f["name"] for f in nested["PartC"]["features"]] == [
        "Boss1",
        "Fillet1",
        "Cut1",
    ]


def test_build_component_tree_excludes_marker_rows_from_features() -> None:
    """UnresolvedComponent/Component marker rows create a node but aren't feature entries."""
    features = [
        {
            "name": "Missing-1",
            "type": "UnresolvedComponent",
            "component": "Missing-1",
            "component_path": None,
            "component_parent": None,
        },
        {
            "name": "DeepSub-1",
            "type": "Component",
            "component": "DeepSub-1",
            "component_path": "C:/DeepSub.sldasm",
            "component_parent": None,
        },
    ]
    tree = build_component_tree(features)
    assert set(tree["components"].keys()) == {"Missing-1", "DeepSub-1"}
    assert tree["components"]["Missing-1"]["features"] == []
    assert tree["components"]["DeepSub-1"]["features"] == []
    assert tree["components"]["DeepSub-1"]["path"] == "C:/DeepSub.sldasm"
