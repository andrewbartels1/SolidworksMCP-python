"""Tests for the rebuild-error explanation layer (pure, no COM)."""

from __future__ import annotations

from solidworks_mcp.adapters.solidworks import rebuild_diagnostics as rd
from solidworks_mcp.adapters.sw_feature_errors import SW_FEATURE_ERRORS


def test_every_curated_code_exists_in_generated_enum() -> None:
    """Curated hints only key real swFeatureError_e values."""
    assert set(rd._CODE_HINTS) <= set(SW_FEATURE_ERRORS)


def test_generated_enum_has_known_anchor_values() -> None:
    """Spot-check values read from swconst.tlb (R2026x)."""
    assert SW_FEATURE_ERRORS[0] == "swFeatureErrorNone"
    assert SW_FEATURE_ERRORS[1] == "swFeatureErrorUnknown"
    assert SW_FEATURE_ERRORS[13] == "swFeatureErrorFilletNoEdge"
    assert SW_FEATURE_ERRORS[71] == "swFeatureErrorCutNotIntersectModel"


def test_code_name_falls_back_for_unknown_code() -> None:
    """An unmapped code is reported as 'code <n>'."""
    assert rd.code_name(9999) == "code 9999"


def test_exact_code_hint_wins() -> None:
    """A curated code gives its own description and hint."""
    entry = rd.explain(
        rd.RawRebuildIssue(
            "Fillet1",
            "Fillet",
            13,
            False,
            [rd.ParentInfo("Boss-Extrude1", "Extrusion")],
        )
    )
    assert entry["code_name"] == "swFeatureErrorFilletNoEdge"
    assert entry["severity"] == "error"
    assert "edge" in entry["description"].lower()
    assert "select_face_edges" in entry["hint"]
    assert entry["parents"] == [{"name": "Boss-Extrude1", "type": "Extrusion"}]


def test_unknown_code_uses_feature_type_hint() -> None:
    """Code 1 on an extrusion falls back to the extrusion hint."""
    entry = rd.explain(rd.RawRebuildIssue("Boss-Extrude2", "Extrusion", 1, False))
    assert entry["code_name"] == "swFeatureErrorUnknown"
    assert "sketch" in entry["hint"].lower()
    assert "Boss-Extrude2" in entry["description"]


def test_empty_parent_sketch_overrides_other_hints() -> None:
    """A parent sketch with zero segments is named in the hint."""
    entry = rd.explain(
        rd.RawRebuildIssue(
            "Boss-Extrude2",
            "Extrusion",
            1,
            False,
            [rd.ParentInfo("Sketch2", "ProfileFeature", 0)],
        )
    )
    assert "Sketch2" in entry["hint"]
    assert "no geometry" in entry["hint"]
    assert entry["parents"] == [
        {"name": "Sketch2", "type": "ProfileFeature", "segment_count": 0}
    ]


def test_unknown_type_and_code_gets_generic_hint() -> None:
    """Nothing specific known -> generic hint."""
    entry = rd.explain(rd.RawRebuildIssue("Thing1", "Mystery", 4242, True))
    assert entry["hint"] == rd.GENERIC_HINT
    assert entry["severity"] == "warning"
    assert entry["code_name"] == "code 4242"


def test_summarize_errors_warnings_and_clean() -> None:
    """Message and counts reflect severities."""
    err = {"feature": "A", "severity": "error"}
    warn = {"feature": "B", "severity": "warning"}
    assert rd.summarize([err, warn])[:2] == (1, 1)
    assert "A" in rd.summarize([err, warn])[2]
    n_err, n_warn, msg = rd.summarize([warn])
    assert (n_err, n_warn) == (0, 1) and "warning" in msg
    assert rd.summarize([]) == (0, 0, "Rebuilt cleanly; no rebuild errors.")


def test_ice_type_gets_neutral_extrude_hint_and_readable_label() -> None:
    """GetTypeName2 'ICE' (live: a boss extrude) is described as an Extrude,
    and its hint covers boss and cut alike."""
    entry = rd.explain(rd.RawRebuildIssue("Boss-Extrude2", "ICE", 1, False))
    assert entry["description"].startswith("Extrude 'Boss-Extrude2'")
    assert "extrude" in entry["hint"].lower()
    assert "cut" in entry["hint"].lower()
