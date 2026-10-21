"""rebuild_model diagnostics with fake COM objects (#106).

Covers both collection sources (GetWhatsWrong, then the GetErrorCode2 tree
walk fallback), parent/sketch inspection, and the adapter-level status rules:
errors -> ERROR carrying data, warnings only -> SUCCESS.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import rebuild_inspector as ri
from solidworks_mcp.adapters.solidworks.io import SolidWorksIOMixin


class _Feature:
    def __init__(  # noqa: PLR0913
        self,
        name: str,
        kind: str,
        code: int = 0,
        warning: bool = False,
        parents: list[_Feature] | None = None,
        segments: list[Any] | None = None,
        suppressed: bool = False,
    ) -> None:
        self.Name, self._kind, self._code, self._warning = name, kind, code, warning
        self._parents = parents or []
        self._segments = segments
        self._suppressed = suppressed
        self.next: _Feature | None = None

    def GetTypeName2(self) -> str:  # noqa: N802
        return self._kind

    def GetParents(self) -> list[_Feature]:  # noqa: N802
        return self._parents

    def GetNextFeature(self):  # noqa: ANN201, N802
        return self.next

    def IsSuppressed(self) -> bool:  # noqa: N802
        return self._suppressed

    def GetErrorCode2(self, is_warning: Any) -> int:  # noqa: N802
        is_warning.value = self._warning
        return self._code

    def GetSpecificFeature2(self):  # noqa: ANN201, N802
        if self._segments is None:
            return None
        return SimpleNamespace(GetSketchSegments=lambda: self._segments or None)


def _chain(*features: _Feature) -> _Feature:
    for a, b in zip(features, features[1:], strict=False):
        a.next = b
    return features[0]


class _Ext:
    def __init__(self, issues: list[tuple[_Feature, int, bool]] | None) -> None:
        self._issues = issues  # None -> GetWhatsWrong unusable

    def GetWhatsWrongCount(self) -> int:  # noqa: N802
        return len(self._issues or []) if self._issues is not None else 1

    def GetWhatsWrong(self, feats: Any, codes: Any, warns: Any) -> bool:  # noqa: N802
        if self._issues is None:
            raise RuntimeError("Parameter not optional.")
        feats.value = tuple(i[0] for i in self._issues)
        codes.value = tuple(i[1] for i in self._issues)
        warns.value = tuple(i[2] for i in self._issues)
        return True


def _model(first: _Feature, issues, rebuild_ok: bool = True) -> SimpleNamespace:  # noqa: ANN001
    return SimpleNamespace(
        Extension=_Ext(issues),
        FirstFeature=lambda: first,
        ForceRebuild3=lambda _top: rebuild_ok,
    )


class _Adapter:
    def __init__(self, model: Any) -> None:
        self.currentModel = model

    def _attempt(self, operation, default=None):  # noqa: ANN001, ANN202
        try:
            return operation()
        except Exception:  # noqa: BLE001
            return default

    def _handle_com_operation(self, name, operation, *args):  # noqa: ANN001, ANN202
        try:
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS, data=operation(*args)
            )
        except Exception as e:  # noqa: BLE001
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )


class _IO(SolidWorksIOMixin):
    def __init__(self, adapter: _Adapter) -> None:
        self._inner = adapter

    @staticmethod
    def _adapter(self_: Any) -> _Adapter:  # noqa: D102
        return self_._inner


def _broken_boss() -> tuple[_Feature, _Feature]:
    sketch = _Feature("Sketch2", "ProfileFeature", segments=[])
    boss = _Feature("Boss-Extrude2", "Extrusion", code=1, parents=[sketch])
    return boss, sketch


# ---- collection sources ----------------------------------------------------


def test_whats_wrong_source_reports_parents_and_empty_sketch() -> None:
    """GetWhatsWrong output becomes issues with parent type + segment count."""
    boss, sketch = _broken_boss()
    model = _model(_chain(sketch, boss), [(boss, 1, False)])
    issues = ri.collect_rebuild_issues(_Adapter(model), model)
    assert len(issues) == 1
    issue = issues[0]
    assert (issue.feature, issue.type, issue.code, issue.is_warning) == (
        "Boss-Extrude2",
        "Extrusion",
        1,
        False,
    )
    assert issue.parents[0].name == "Sketch2"
    assert issue.parents[0].segment_count == 0


def test_clean_model_short_circuits_on_zero_count() -> None:
    """GetWhatsWrongCount() == 0 -> no issues, no further calls needed."""
    feature = _Feature("Boss-Extrude1", "Extrusion")
    model = _model(feature, [])
    assert ri.collect_rebuild_issues(_Adapter(model), model) == []


def test_tree_walk_fallback_skips_suppressed_and_reads_warning() -> None:
    """When GetWhatsWrong is unusable the GetErrorCode2 walk is used."""
    ok = _Feature("Boss-Extrude1", "Extrusion")
    warn = _Feature("Fillet1", "Fillet", code=18, warning=True)
    hidden = _Feature("Cut-Extrude1", "Cut", code=71, suppressed=True)
    model = _model(_chain(ok, warn, hidden), None)
    issues = ri.collect_rebuild_issues(_Adapter(model), model)
    assert [(i.feature, i.code, i.is_warning) for i in issues] == [
        ("Fillet1", 18, True)
    ]


# ---- adapter status rules ----------------------------------------------------


@pytest.mark.asyncio
async def test_rebuild_with_error_is_error_carrying_data() -> None:
    """A remaining error -> ERROR, message names it, data has the hint."""
    boss, sketch = _broken_boss()
    model = _model(_chain(sketch, boss), [(boss, 1, False)])
    result = await _IO(_Adapter(model)).rebuild_model()
    assert result.status == AdapterResultStatus.ERROR
    assert "Boss-Extrude2" in (result.error or "")
    assert result.data["error_count"] == 1
    entry = result.data["errors"][0]
    assert entry["code_name"] == "swFeatureErrorUnknown"
    assert "Sketch2" in entry["hint"] and "no geometry" in entry["hint"]


@pytest.mark.asyncio
async def test_rebuild_warnings_only_is_success() -> None:
    """Only warnings -> SUCCESS with them listed."""
    fillet = _Feature("Fillet1", "Fillet", code=18, warning=True)
    model = _model(fillet, [(fillet, 18, True)])
    result = await _IO(_Adapter(model)).rebuild_model(top_level_only=True)
    assert result.is_success
    assert result.data["top_level_only"] is True
    assert result.data["warning_count"] == 1
    assert result.data["errors"][0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_rebuild_clean_and_failure_paths() -> None:
    """Clean -> SUCCESS with no errors; ForceRebuild3 False -> clean ERROR."""
    feature = _Feature("Boss-Extrude1", "Extrusion")
    clean = await _IO(_Adapter(_model(feature, []))).rebuild_model()
    assert clean.is_success and clean.data["errors"] == []
    assert clean.data["summary"] == "Rebuilt cleanly; no rebuild errors."

    failed = await _IO(_Adapter(_model(feature, [], rebuild_ok=False))).rebuild_model()
    assert failed.is_error
    assert "listed no failing feature" in (failed.error or "")

    none = await _IO(_Adapter(None)).rebuild_model()
    assert none.is_error and none.error == "No active model"


@pytest.mark.asyncio
async def test_rebuild_false_with_issues_still_reports_them() -> None:
    """ForceRebuild3 returns False when a feature fails (live 2026-10-13):
    the diagnostics must still come back, not a generic failure."""
    boss, sketch = _broken_boss()
    model = _model(_chain(sketch, boss), [(boss, 1, False)], rebuild_ok=False)
    result = await _IO(_Adapter(model)).rebuild_model()
    assert result.is_error
    assert "Boss-Extrude2" in (result.error or "")
    assert result.data["rebuilt"] is False
    assert result.data["errors"][0]["feature"] == "Boss-Extrude2"


def test_extra_warning_flags_are_trimmed_not_fatal() -> None:
    """Review #4: more warning flags than features must not raise."""
    boss, sketch = _broken_boss()
    model = _model(_chain(sketch, boss), [(boss, 1, False)])

    def _whats_wrong(feats, codes, warns):  # noqa: ANN001, ANN202
        feats.value, codes.value, warns.value = (boss,), (1,), (False, True, True)
        return True

    model.Extension.GetWhatsWrong = _whats_wrong
    issues = ri.collect_rebuild_issues(_Adapter(model), model)
    assert [(i.feature, i.is_warning) for i in issues] == [("Boss-Extrude2", False)]


def test_tree_walk_visits_sub_features() -> None:
    """Review #6: a sketch absorbed under a cut is checked in the fallback."""
    bad_sketch = _Feature("Sketch2", "ProfileFeature", code=51)
    cut = _Feature("Cut-Extrude1", "Cut")
    cut.GetFirstSubFeature = lambda: bad_sketch  # type: ignore[attr-defined]
    bad_sketch.GetNextSubFeature = lambda: None  # type: ignore[attr-defined]
    model = _model(cut, None)  # GetWhatsWrong unusable -> fallback walk
    issues = ri.collect_rebuild_issues(_Adapter(model), model)
    assert [(i.feature, i.code) for i in issues] == [("Sketch2", 51)]


@pytest.mark.asyncio
async def test_rebuild_false_with_only_warnings_keeps_them() -> None:
    """Review #5: ForceRebuild3 False + warnings only -> ERROR that still
    carries the warnings in data."""
    fillet = _Feature("Fillet1", "Fillet", code=18, warning=True)
    model = _model(fillet, [(fillet, 18, True)], rebuild_ok=False)
    result = await _IO(_Adapter(model)).rebuild_model()
    assert result.is_error
    assert "listed no failing feature" in (result.error or "")
    assert "Fillet1" in (result.error or "")
    assert result.data["warning_count"] == 1
    assert result.data["errors"][0]["feature"] == "Fillet1"


class _UnreadableSketch(_Feature):
    """A sketch parent whose segment list raises when read."""

    def GetSpecificFeature2(self):  # noqa: ANN201, N802
        def _boom() -> None:
            raise RuntimeError("segments unavailable")

        return SimpleNamespace(GetSketchSegments=_boom)


@pytest.mark.parametrize(
    "sketch",
    [
        _Feature("Sketch1", "ProfileFeature", segments=None),  # no sketch object
        _UnreadableSketch("Sketch1", "ProfileFeature"),
    ],
)
def test_unreadable_parent_sketch_reports_no_segment_count(sketch: _Feature) -> None:
    boss = _Feature("Boss-Extrude1", "Extrusion", code=1, parents=[sketch])
    adapter = _Adapter(_model(boss, [(boss, 1, False)]))

    (issue,) = ri.collect_rebuild_issues(adapter, adapter.currentModel)

    assert issue.parents[0].name == "Sketch1"
    assert issue.parents[0].segment_count is None


class _MismatchedExt(_Ext):
    """GetWhatsWrong returning fewer codes than features."""

    def GetWhatsWrong(self, feats: Any, codes: Any, warns: Any) -> bool:  # noqa: N802
        feats.value = tuple(i[0] for i in self._issues or [])
        codes.value = ()
        warns.value = ()
        return True


def test_mismatched_whats_wrong_arrays_fall_back_to_the_tree_walk() -> None:
    boss = _Feature("Boss-Extrude1", "Extrusion", code=1)
    model = _model(boss, [(boss, 1, False)])
    model.Extension = _MismatchedExt([(boss, 1, False)])

    issues = ri.collect_rebuild_issues(_Adapter(model), model)

    assert [(i.feature, i.code) for i in issues] == [("Boss-Extrude1", 1)]


@pytest.mark.asyncio
async def test_rebuild_call_failure_reads_as_a_plain_sentence() -> None:
    """A raising ForceRebuild3 is an ERROR without the generic op prefix."""

    def broken(_top):
        raise RuntimeError("The object invoked has disconnected from its clients.")

    model = SimpleNamespace(ForceRebuild3=broken)
    result = await _IO(_Adapter(model)).rebuild_model()
    assert result.is_error
    assert result.error == "The object invoked has disconnected from its clients."
