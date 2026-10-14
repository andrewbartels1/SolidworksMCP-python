"""Collect rebuild errors/warnings from the active SolidWorks model (COM side).

Feeds :mod:`rebuild_diagnostics`, which turns each raw issue into a
description and fix hint. Two sources, in the order chosen from the live probe
(R2026x, 2026-10-13, see the #106 change's design.md):

1. ``IModelDocExtension::GetWhatsWrong`` with three byref VARIANT out-params
   - one call returns every flagged feature, its code and warning flag.
2. Fallback: walk the feature tree calling
   ``IFeature::GetErrorCode2(byref IsWarning)`` on each unsuppressed feature.
"""

from __future__ import annotations

from typing import Any

from .com_utils import as_list as _as_list
from .com_utils import attempt as _attempt
from .com_utils import flag as _flag
from .io import _byref_bool, _byref_variant
from .rebuild_diagnostics import ParentInfo, RawRebuildIssue

_FEATURE_MEMBERS = (
    "GetTypeName2",
    "GetParents",
    "GetNextFeature",
    "GetFirstSubFeature",
    "GetNextSubFeature",
    "GetErrorCode2",
    "IsSuppressed",
    "GetSpecificFeature2",
)
_MAX_FEATURES = 10000  # runaway guard, same as the selector's tree walk


def _sketch_segment_count(adapter: Any, feature: Any) -> int | None:
    """Segment count of a sketch feature, or None when not readable."""
    sketch = _attempt(adapter, lambda: feature.GetSpecificFeature2())
    if sketch is None:
        return None
    _flag(adapter, sketch, "GetSketchSegments")
    segments = _attempt(adapter, lambda: sketch.GetSketchSegments(), default=False)
    if segments is False:
        return None
    return len(_as_list(segments))


def _parents(adapter: Any, feature: Any) -> list[ParentInfo]:
    """Describe the features/sketches ``feature`` depends on."""
    out = []
    for parent in _as_list(_attempt(adapter, lambda: feature.GetParents())):
        _flag(adapter, parent, *_FEATURE_MEMBERS)
        name = str(_attempt(adapter, lambda p=parent: p.Name, "") or "")
        kind = str(_attempt(adapter, lambda p=parent: p.GetTypeName2(), "") or "")
        segments = (
            _sketch_segment_count(adapter, parent) if kind == "ProfileFeature" else None
        )
        out.append(ParentInfo(name=name, type=kind, segment_count=segments))
    return out


def _issue(adapter: Any, feature: Any, code: int, is_warning: bool) -> RawRebuildIssue:
    _flag(adapter, feature, *_FEATURE_MEMBERS)
    return RawRebuildIssue(
        feature=str(_attempt(adapter, lambda: feature.Name, "") or ""),
        type=str(_attempt(adapter, lambda: feature.GetTypeName2(), "") or ""),
        code=int(code),
        is_warning=bool(is_warning),
        parents=_parents(adapter, feature),
    )


def _from_whats_wrong(adapter: Any, model: Any) -> list[RawRebuildIssue] | None:
    """Source 1: one GetWhatsWrong call. None when the call is unusable."""
    ext = _attempt(adapter, lambda: model.Extension)
    if ext is None:
        return None
    _flag(adapter, ext, "GetWhatsWrongCount", "GetWhatsWrong")
    count = _attempt(adapter, lambda: ext.GetWhatsWrongCount())
    if isinstance(count, (int, float)) and int(count) == 0:
        return []
    features, codes, warnings = _byref_variant(), _byref_variant(), _byref_variant()
    if _attempt(adapter, lambda: ext.GetWhatsWrong(features, codes, warnings)) is None:
        return None
    feats = _as_list(features.value)
    errs = _as_list(codes.value)
    warns = _as_list(warnings.value)
    if not feats or len(errs) != len(feats):
        return None
    warns = (warns + [False] * len(feats))[: len(feats)]
    return [
        _issue(adapter, f, int(c), bool(w))
        for f, c, w in zip(feats, errs, warns, strict=True)
        if f is not None
    ]


def _check(adapter: Any, feature: Any, issues: list[RawRebuildIssue]) -> None:
    """Append ``feature``'s rebuild issue (if any) to ``issues``."""
    if _attempt(adapter, lambda: feature.IsSuppressed(), False):
        return
    is_warning = _byref_bool()
    code = _attempt(adapter, lambda: feature.GetErrorCode2(is_warning), 0)
    if isinstance(code, (int, float)) and int(code) != 0:
        issues.append(_issue(adapter, feature, int(code), bool(is_warning.value)))


def _from_tree_walk(adapter: Any, model: Any) -> list[RawRebuildIssue]:
    """Source 2: per-feature GetErrorCode2 over the unsuppressed tree.

    Visits each top-level feature and its sub-features (e.g. the sketch an
    extrude or cut absorbed), since a sketch error lives on the sketch.
    """
    issues: list[RawRebuildIssue] = []
    feature = _attempt(adapter, lambda: model.FirstFeature())
    guard = 0
    while feature is not None and guard < _MAX_FEATURES:
        guard += 1
        _flag(adapter, feature, *_FEATURE_MEMBERS)
        current = feature
        _check(adapter, current, issues)
        sub = _attempt(adapter, lambda f=current: f.GetFirstSubFeature())
        while sub is not None and guard < _MAX_FEATURES:
            guard += 1
            _flag(adapter, sub, *_FEATURE_MEMBERS)
            sub_current = sub
            _check(adapter, sub_current, issues)
            sub = _attempt(adapter, lambda s=sub_current: s.GetNextSubFeature())
        feature = _attempt(adapter, lambda f=current: f.GetNextFeature())
    return issues


def collect_rebuild_issues(adapter: Any, model: Any) -> list[RawRebuildIssue]:
    """Return every rebuild error/warning on ``model`` after a rebuild.

    Args:
        adapter: A connected adapter (for ``_attempt``).
        model: The active ``IModelDoc2``.

    Returns:
        list[RawRebuildIssue]: Empty when the model is clean.
    """
    issues = _from_whats_wrong(adapter, model)
    if issues is None:
        issues = _from_tree_walk(adapter, model)
    return issues
