"""Helpers for classifying SolidWorks model families from feature-tree snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_SHEET_METAL_TOKENS = (
    "sheet-metal",
    "sheet metal",
    "base-flange",
    "edge-flange",
    "sketched bend",
    "miter flange",
    "hem",
    "jog",
    "unfold",
    "fold",
    "flatten",
    "flat-pattern",
)

_ADVANCED_SOLID_TOKENS = (
    "loft",
    "boundary",
    "sweep",
    "shell",
    "surface",
    "split",
    "combine",
    "rib",
    "dome",
)

_REVOLVE_TOKENS = (
    "revolve",
    "bossrevolve",
    "boss-revolve",
    "cutrevolve",
    "cut-revolve",
)

_EXTRUDE_TOKENS = (
    "extrude",
    "boss-extrude",
    "cut-extrude",
    "bosscutextrude",
    "featureextrusion",
)

_ASSEMBLY_TOKENS = ("mate", "component", "subassembly")
_DRAWING_TOKENS = (
    "sheet format",
    "drawing view",
    "section view",
    "detail view",
    "model view",
)


def _as_lower_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _feature_text(feature: Mapping[str, Any]) -> str:
    name = _as_lower_text(feature.get("name"))
    feature_type = _as_lower_text(feature.get("type"))
    return f"{name} {feature_type}".strip()


def _has_any(texts: list[str], tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens for text in texts)


def _match_examples(
    texts: list[str], tokens: tuple[str, ...], limit: int = 4
) -> list[str]:
    matches: list[str] = []
    for text in texts:
        if any(token in text for token in tokens):
            matches.append(text)
        if len(matches) >= limit:
            break
    return matches


def classify_feature_tree_snapshot(
    model_info: Mapping[str, Any] | None,
    features: list[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Classify a model family from model-info and feature-tree snapshots.

    The output is intentionally simple and explainable so agents can use it as a
    planning primitive rather than as a black-box prediction.
    """

    feature_list = list(features or [])
    feature_texts = [_feature_text(feature) for feature in feature_list]
    document_type = _as_lower_text((model_info or {}).get("type")) or "unknown"

    evidence: list[str] = []
    warnings: list[str] = []
    next_actions: list[str] = []

    family = "unknown"
    workflow = "inspect-more"
    confidence = "low"
    needs_vba = False

    if document_type == "assembly" or _has_any(feature_texts, _ASSEMBLY_TOKENS):
        family = "assembly"
        workflow = "assembly-planning"
        confidence = "high" if document_type == "assembly" else "medium"
        evidence.append("Assembly document or mate/component evidence detected")
        next_actions.extend(
            [
                "List components and mates before planning inserts or edits",
                "Delegate part-level reconstruction for each component separately",
            ]
        )
    elif document_type == "drawing" or _has_any(feature_texts, _DRAWING_TOKENS):
        family = "drawing"
        workflow = "drawing-review"
        confidence = "high" if document_type == "drawing" else "medium"
        evidence.append("Drawing document or drawing-view evidence detected")
        next_actions.append("Use drawing tools instead of part-modeling tools")
    elif _has_any(feature_texts, _SHEET_METAL_TOKENS):
        family = "sheet_metal"
        workflow = "vba-sheet-metal"
        confidence = "high"
        needs_vba = True
        evidence.extend(
            _match_examples(feature_texts, _SHEET_METAL_TOKENS)
            or ["Sheet metal features detected in the tree"]
        )
        next_actions.extend(
            [
                "Preserve base-flange and bend dependency order",
                "If cuts appear between Unfold and Fold, keep them in flat-pattern state",
                "Prefer a VBA-aware reconstruction plan until direct sheet metal tools exist",
            ]
        )
    elif _has_any(feature_texts, _ADVANCED_SOLID_TOKENS):
        family = "advanced_solid"
        workflow = "vba-advanced-solid"
        confidence = "medium"
        needs_vba = True
        evidence.extend(
            _match_examples(feature_texts, _ADVANCED_SOLID_TOKENS)
            or ["Advanced solid or surface features detected"]
        )
        next_actions.extend(
            [
                "Plan around loft/sweep/shell boundaries before issuing build commands",
                "Prefer macro-backed execution for unsupported direct-MCP features",
            ]
        )
    elif _has_any(feature_texts, _REVOLVE_TOKENS):
        family = "revolve"
        workflow = "direct-mcp-revolve"
        confidence = "high"
        evidence.extend(
            _match_examples(feature_texts, _REVOLVE_TOKENS)
            or ["Revolve features detected"]
        )
        next_actions.extend(
            [
                "Locate the axis sketch or centerline before recreating the profile",
                "Verify the half-profile closes on the revolve axis",
            ]
        )
    elif _has_any(feature_texts, _EXTRUDE_TOKENS):
        family = "extrude"
        workflow = "direct-mcp-extrude"
        confidence = "high"
        evidence.extend(
            _match_examples(feature_texts, _EXTRUDE_TOKENS)
            or ["Extrude features detected"]
        )
        next_actions.extend(
            [
                "Read the driving sketch before recreating downstream cuts or fillets",
                "Verify closed-loop profiles before extrusion",
            ]
        )
    else:
        non_reference_count = 0
        sketch_like_count = 0
        for feature in feature_list:
            feature_type = _as_lower_text(feature.get("type"))
            if feature_type and feature_type not in {
                "refplane",
                "originprofilefeature",
            }:
                non_reference_count += 1
            if feature_type in {"profilefeature", "3dprofilefeature", "sketch"}:
                sketch_like_count += 1

        if sketch_like_count > 0 and sketch_like_count == non_reference_count:
            family = "sketch_only"
            workflow = "inspect-more"
            confidence = "low"
            evidence.append("Only sketch-like features were found in the tree snapshot")
            warnings.append(
                "Feature tree may be incomplete for this adapter/runtime; do not infer the 3D family from sketches alone"
            )
            next_actions.extend(
                [
                    "Combine feature-tree output with mass properties and exported images",
                    "Prefer reading the original file in SolidWorks before planning a rebuild",
                ]
            )
        else:
            warnings.append(
                "No strong feature-family evidence found; keep planning provisional"
            )
            next_actions.extend(
                [
                    "Inspect more of the model state before building",
                    "Avoid committing to direct-MCP or VBA-only paths until evidence improves",
                ]
            )

    return {
        "document_type": document_type or "unknown",
        "family": family,
        "recommended_workflow": workflow,
        "confidence": confidence,
        "needs_vba": needs_vba,
        "evidence": evidence,
        "warnings": warnings,
        "next_actions": next_actions,
        "feature_count": len(feature_list),
    }
