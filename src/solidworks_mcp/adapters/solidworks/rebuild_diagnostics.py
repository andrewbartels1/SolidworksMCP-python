"""Turn SolidWorks rebuild error codes into descriptions and fix hints.

Pure functions, no COM: the adapter collects ``(feature, type, code,
is_warning, parents)`` from ``IModelDocExtension::GetWhatsWrong`` and this
module explains each one so an LLM caller can repair the model rather than
just learning that the rebuild "didn't work".

Hints are chosen most-specific first: an exact ``swFeatureError_e`` code, then
the feature type (``swFeatureErrorUnknown`` - code 1 - is what SolidWorks
reports for many common failures, e.g. an extrude whose sketch was emptied,
so the type is often the only useful signal), then a parent sketch that has
no geometry, then a generic fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..sw_feature_errors import SW_FEATURE_ERRORS

GENERIC_HINT = (
    "Inspect the parents listed for this feature: re-target any missing "
    "edge/face/sketch reference, fix the parent sketch, or suppress/delete the "
    "feature and recreate it."
)

# Exact-code hints. Keys MUST exist in SW_FEATURE_ERRORS (enforced by tests).
_CODE_HINTS: dict[int, tuple[str, str]] = {
    10: (
        "The fillet could not find a closed loop of edges.",
        "Re-select the fillet edges (e.g. select_face_edges then add_fillet "
        "with empty edge_names) or delete and recreate the fillet.",
    ),
    11: (
        "A face the fillet referenced no longer exists.",
        "Re-select the fillet's faces/edges with select_face_edges, or delete "
        "and recreate the fillet.",
    ),
    12: (
        "The fillet radius is invalid.",
        "Set a positive radius smaller than the adjacent faces allow.",
    ),
    13: (
        "An edge the fillet referenced no longer exists (often after an "
        "earlier dimension or feature change).",
        "Re-select the edges with select_face_edges (prefer whole-face "
        "selection) and recreate the fillet.",
    ),
    15: (
        "The fillet radius is too small for the geometry.",
        "Increase the fillet radius.",
    ),
    18: (
        "The fillet radius is too big for the adjacent faces.",
        "Reduce the fillet radius below the thickness of the faces it joins.",
    ),
    19: (
        "The fillet radius is too big for the adjacent faces.",
        "Reduce the fillet radius below the thickness of the faces it joins.",
    ),
    30: (
        "The extrusion would create disjoint (disconnected) bodies.",
        "Change the extrude depth/end condition so the result touches the "
        "existing body, or enable merge-off / multibody intentionally.",
    ),
    31: (
        "The extrusion's end condition found no end (e.g. Up To Surface target "
        "missing).",
        "Re-select the up-to reference or switch the end condition to Blind "
        "with an explicit depth.",
    ),
    33: (
        "The cut profile mixes open and closed contours.",
        "Edit the cut's sketch so it contains only closed contours.",
    ),
    34: (
        "The cut profile is invalid (open, overlapping or self-intersecting).",
        "Edit the cut's sketch: close every contour and remove overlaps.",
    ),
    36: (
        "The boss profile mixes open and closed contours.",
        "Edit the boss sketch so it contains only closed contours.",
    ),
    37: (
        "The boss profile is invalid (open, overlapping or self-intersecting).",
        "Edit the boss sketch: close every contour and remove overlaps.",
    ),
    43: (
        "A mate references geometry that no longer exists (dangling).",
        "Delete the mate and re-mate the components to existing faces/edges.",
    ),
    46: (
        "The assembly is over-defined by mates.",
        "Delete or suppress the conflicting mate(s).",
    ),
    48: ("A mate is broken.", "Delete the mate and recreate it."),
    51: (
        "The sketch's external reference could not be resolved.",
        "Edit the sketch and repair or delete its dangling relations.",
    ),
    71: (
        "The cut does not intersect the model.",
        "Move the cut sketch onto/inside the body, flip the cut direction, or "
        "increase its depth.",
    ),
    72: (
        "The sketch contains a self-intersecting contour.",
        "Edit the sketch and remove the crossing segments.",
    ),
    73: (
        "Items the feature needs are missing.",
        "Re-select the feature's missing references or recreate the feature.",
    ),
}

# Feature-type hints, used when the code alone is not specific
# (``swFeatureErrorUnknown``) or has no curated hint. Keys are
# ``IFeature::GetTypeName2`` values.
_TYPE_HINTS: dict[str, str] = {
    "Extrusion": (
        "Check the boss's parent sketch: it must contain at least one closed "
        "contour, and the depth/end condition must reach geometry."
    ),
    "Cut": (
        "Check the cut's parent sketch has a closed contour that overlaps the "
        "body, and that the cut direction/depth actually removes material."
    ),
    # "ICE" is what GetTypeName2 reports for extrudes created through the
    # API - boss or cut (observed live on R2026x for a boss extrude).
    "ICE": (
        "Check the extrude's parent sketch: it must contain a closed contour, "
        "and the depth/end condition must reach (or, for a cut, overlap) the body."
    ),
    "Fillet": (
        "The fillet's edges/faces probably changed. Re-select them with "
        "select_face_edges and recreate the fillet, or reduce the radius."
    ),
    "Chamfer": (
        "The chamfer's edges probably changed. Re-select them with "
        "select_face_edges and recreate the chamfer, or reduce the distance."
    ),
    "ProfileFeature": (
        "The sketch itself has a problem (dangling or conflicting relations, "
        "or a reference to deleted geometry). Edit the sketch to repair it."
    ),
    "RefPlane": (
        "The reference plane lost the face/plane it was defined from. Redefine "
        "it from existing geometry."
    ),
}

#: Readable names for GetTypeName2 values used in descriptions.
_TYPE_LABELS: dict[str, str] = {
    "ICE": "Extrude",
    "Extrusion": "Boss-extrude",
    "Cut": "Cut-extrude",
    "ProfileFeature": "Sketch",
    "RefPlane": "Reference plane",
}

_EMPTY_SKETCH_HINT = (
    "Parent sketch '{name}' has no geometry. Add a closed profile to it (or "
    "delete this feature)."
)


@dataclass(frozen=True)
class ParentInfo:
    """A feature the failing feature depends on.

    Attributes:
        name: The parent feature or sketch name.
        type: Its ``GetTypeName2`` value (``""`` when unknown).
        segment_count: For sketches, how many segments it has; ``None`` when
            not a sketch or not readable.
    """

    name: str
    type: str = ""
    segment_count: int | None = None


@dataclass(frozen=True)
class RawRebuildIssue:
    """One raw ``GetWhatsWrong`` entry as collected from COM."""

    feature: str
    type: str
    code: int
    is_warning: bool
    parents: list[ParentInfo] = field(default_factory=list)


def code_name(code: int) -> str:
    """Return the ``swFeatureError_e`` member name, or ``"code <n>"``."""
    return SW_FEATURE_ERRORS.get(code, f"code {code}")


def explain(issue: RawRebuildIssue) -> dict[str, Any]:
    """Build the caller-facing diagnostic entry for one rebuild issue.

    Args:
        issue: The raw entry collected from SolidWorks.

    Returns:
        dict[str, Any]: ``feature``, ``type``, ``code``, ``code_name``,
        ``severity``, ``description``, ``parents`` and ``hint``.
    """
    description, hint = _CODE_HINTS.get(issue.code, ("", ""))
    empty_parent = next(
        (
            p
            for p in issue.parents
            if p.type == "ProfileFeature" and p.segment_count == 0
        ),
        None,
    )
    if empty_parent is not None:
        hint = _EMPTY_SKETCH_HINT.format(name=empty_parent.name)
    elif not hint:
        hint = _TYPE_HINTS.get(issue.type, GENERIC_HINT)
    if not description:
        description = (
            f"{_TYPE_LABELS.get(issue.type, issue.type or 'Feature')} "
            f"'{issue.feature}' failed to rebuild "
            f"({code_name(issue.code)})."
        )
    return {
        "feature": issue.feature,
        "type": issue.type,
        "code": issue.code,
        "code_name": code_name(issue.code),
        "severity": "warning" if issue.is_warning else "error",
        "description": description,
        "parents": [
            {"name": p.name, "type": p.type}
            | (
                {"segment_count": p.segment_count}
                if p.segment_count is not None
                else {}
            )
            for p in issue.parents
        ],
        "hint": hint,
    }


def summarize(entries: list[dict[str, Any]]) -> tuple[int, int, str]:
    """Count errors/warnings and build the one-line status message.

    Args:
        entries: Output of :func:`explain` for every issue.

    Returns:
        tuple[int, int, str]: ``(error_count, warning_count, message)``.
    """
    errors = [e["feature"] for e in entries if e["severity"] == "error"]
    warnings = [e["feature"] for e in entries if e["severity"] == "warning"]
    if errors:
        message = (
            f"Rebuild left {len(errors)} feature error(s): {', '.join(errors)}. "
            "See data.errors for each cause and hint."
        )
    elif warnings:
        message = f"Rebuilt with {len(warnings)} warning(s): {', '.join(warnings)}."
    else:
        message = "Rebuilt cleanly; no rebuild errors."
    return len(errors), len(warnings), message
