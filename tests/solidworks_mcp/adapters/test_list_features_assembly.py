"""Regression tests for assembly-aware ``list_features``.

Covers the ``_FeatureSelectionService`` traversal added for GitHub issue #21
and OpenSpec change ``assembly-aware-list-features``: Part documents stay
byte-for-byte unchanged, Assembly documents flatten component features into
the same list tagged with ``component``/``component_path``, suppression is
honored independently per document, sub-assembly recursion is bounded by
``max_assembly_depth``, and an unresolvable component doesn't fail the call.

Uses the same ``SimpleNamespace``-based COM fake pattern as the existing
``test_list_features_*`` tests in ``test_adapters.py`` — no SolidWorks
required.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter


class _Feature:
    """Minimal COM feature fake: Name / GetTypeName2 / IsSuppressed / GetNextFeature."""

    def __init__(self, name: str, feature_type: str, suppressed: bool = False) -> None:
        self.Name = name
        self._feature_type = feature_type
        self._suppressed = suppressed
        self._next: _Feature | None = None

    def GetTypeName2(self) -> str:
        return self._feature_type

    def IsSuppressed(self) -> bool:
        return self._suppressed

    def GetNextFeature(self) -> _Feature | None:
        return self._next


def _chain(*features: _Feature) -> _Feature:
    """Link features into a FirstFeature -> GetNextFeature chain."""
    for a, b in zip(features, features[1:], strict=False):
        a._next = b
    return features[0]


def _part_doc(path: str, title: str, *features: _Feature) -> SimpleNamespace:
    """Build a fake IModelDoc2 Part document with a feature chain."""
    first = _chain(*features) if features else None
    return SimpleNamespace(
        FirstFeature=lambda: first,
        FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: 0),
        GetType=lambda: 1,
        GetPathName=lambda: path,
        GetTitle=lambda: title,
    )


def _component(name: str, resolved_doc: SimpleNamespace | None) -> SimpleNamespace:
    """Build a fake IComponent2: Name2 + GetModelDoc2."""
    return SimpleNamespace(Name2=name, GetModelDoc2=lambda: resolved_doc)


def _assembly_doc(
    path: str,
    title: str,
    components: list[SimpleNamespace],
    *own_features: _Feature,
) -> SimpleNamespace:
    """Build a fake IAssemblyDoc/IModelDoc2 with components + own features."""
    first = _chain(*own_features) if own_features else None
    return SimpleNamespace(
        FirstFeature=lambda: first,
        FeatureManager=SimpleNamespace(GetFeatureCount=lambda _all: 0),
        GetType=lambda: 2,
        GetPathName=lambda: path,
        GetTitle=lambda: title,
        GetComponents=lambda top_level_only=True: components,
    )


def _build_adapter(monkeypatch) -> PyWin32Adapter:
    """Build a PyWin32Adapter with COM/platform checks bypassed, per the
    existing convention in test_adapters.py's ``_build_adapter`` helpers.
    """
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.platform.system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter.pywintypes",
        SimpleNamespace(com_error=RuntimeError),
        raising=False,
    )
    return PyWin32Adapter({})


@pytest.mark.asyncio
async def test_part_document_unchanged(monkeypatch) -> None:
    """A Part document's own features are unaffected, tagged component=None."""
    adapter = _build_adapter(monkeypatch)
    adapter.currentModel = _part_doc(
        "C:\\mock\\Bracket.sldprt",
        "Bracket.SLDPRT",
        _Feature("Front Plane", "RefPlane"),
        _Feature("Boss-Extrude1", "Boss"),
    )

    result = await adapter.list_features(include_suppressed=False)

    assert result.is_success
    assert [row["name"] for row in result.data] == ["Front Plane", "Boss-Extrude1"]
    assert all(row["component"] is None for row in result.data)
    assert all(row["component_path"] is None for row in result.data)


@pytest.mark.asyncio
async def test_assembly_flattens_component_features(monkeypatch) -> None:
    """Assembly features + both components' features appear in one flat list."""
    adapter = _build_adapter(monkeypatch)

    part_a = _part_doc(
        "C:\\mock\\PartA.sldprt", "PartA.SLDPRT", _Feature("Boss-Extrude1", "Boss")
    )
    part_b = _part_doc(
        "C:\\mock\\PartB.sldprt", "PartB.SLDPRT", _Feature("Cut-Extrude1", "Cut")
    )
    components = [_component("PartA-1", part_a), _component("PartB-1", part_b)]
    adapter.currentModel = _assembly_doc(
        "C:\\mock\\Assem1.sldasm",
        "Assem1.SLDASM",
        components,
        _Feature("Mate1", "Mate"),
    )

    result = await adapter.list_features(include_suppressed=False)

    assert result.is_success
    by_name = {row["name"]: row for row in result.data}

    assert by_name["Mate1"]["component"] is None
    assert by_name["Mate1"]["component_path"] is None

    assert by_name["Boss-Extrude1"]["component"] == "PartA-1"
    assert by_name["Boss-Extrude1"]["component_path"] == os.path.abspath(
        "C:\\mock\\PartA.sldprt"
    )

    assert by_name["Cut-Extrude1"]["component"] == "PartB-1"
    assert by_name["Cut-Extrude1"]["component_path"] == os.path.abspath(
        "C:\\mock\\PartB.sldprt"
    )


@pytest.mark.asyncio
async def test_suppression_is_independent_per_component(monkeypatch) -> None:
    """A suppressed feature in one component doesn't affect another."""
    adapter = _build_adapter(monkeypatch)

    part_a = _part_doc(
        "C:\\mock\\PartA.sldprt",
        "PartA.SLDPRT",
        _Feature("Boss-Extrude1", "Boss", suppressed=False),
        _Feature("Fillet1", "Fillet", suppressed=True),
    )
    part_b = _part_doc(
        "C:\\mock\\PartB.sldprt", "PartB.SLDPRT", _Feature("Cut-Extrude1", "Cut")
    )
    components = [_component("PartA-1", part_a), _component("PartB-1", part_b)]
    adapter.currentModel = _assembly_doc(
        "C:\\mock\\Assem1.sldasm", "Assem1.SLDASM", components
    )

    hidden = await adapter.list_features(include_suppressed=False)
    shown = await adapter.list_features(include_suppressed=True)

    hidden_names = {row["name"] for row in hidden.data}
    shown_names = {row["name"] for row in shown.data}

    assert "Fillet1" not in hidden_names
    assert {"Boss-Extrude1", "Cut-Extrude1"} <= hidden_names
    assert "Fillet1" in shown_names


@pytest.mark.asyncio
async def test_subassembly_recursion_within_default_depth(monkeypatch) -> None:
    """A sub-assembly one level deep is expanded at the default depth of 2."""
    adapter = _build_adapter(monkeypatch)

    part_c = _part_doc(
        "C:\\mock\\PartC.sldprt", "PartC.SLDPRT", _Feature("Boss-Extrude1", "Boss")
    )
    sub_assembly = _assembly_doc(
        "C:\\mock\\SubAssem.sldasm",
        "SubAssem.SLDASM",
        [_component("PartC-1", part_c)],
        _Feature("Mate2", "Mate"),
    )
    top_components = [_component("SubAssem-1", sub_assembly)]
    adapter.currentModel = _assembly_doc(
        "C:\\mock\\Top.sldasm", "Top.SLDASM", top_components
    )

    result = await adapter.list_features(include_suppressed=False)

    names = [row["name"] for row in result.data]
    assert "Mate2" in names
    assert "Boss-Extrude1" in names

    by_name = {row["name"]: row for row in result.data}
    # SubAssem-1 is top-level: no parent.
    assert by_name["Mate2"]["component"] == "SubAssem-1"
    assert by_name["Mate2"]["component_parent"] is None
    # PartC-1 is nested inside SubAssem-1: component_parent links it back,
    # distinguishing "nested inside" from merely "also in this assembly".
    assert by_name["Boss-Extrude1"]["component"] == "PartC-1"
    assert by_name["Boss-Extrude1"]["component_parent"] == "SubAssem-1"

    from solidworks_mcp.utils.feature_tree_classifier import build_component_tree

    tree = build_component_tree(result.data)
    assert "PartC-1" in tree["components"]["SubAssem-1"]["components"]
    assert "PartC-1" not in tree["components"]

    by_name = {row["name"]: row for row in result.data}
    assert by_name["Mate2"]["component"] == "SubAssem-1"
    assert by_name["Boss-Extrude1"]["component"] == "PartC-1"


@pytest.mark.asyncio
async def test_subassembly_beyond_depth_limit_is_not_expanded(monkeypatch) -> None:
    """A sub-assembly beyond max_assembly_depth appears as one bare descriptor."""
    adapter = _build_adapter(monkeypatch)

    part_c = _part_doc(
        "C:\\mock\\PartC.sldprt", "PartC.SLDPRT", _Feature("Boss-Extrude1", "Boss")
    )
    sub_assembly = _assembly_doc(
        "C:\\mock\\SubAssem.sldasm",
        "SubAssem.SLDASM",
        [_component("PartC-1", part_c)],
        _Feature("Mate2", "Mate"),
    )
    top_components = [_component("SubAssem-1", sub_assembly)]
    adapter.currentModel = _assembly_doc(
        "C:\\mock\\Top.sldasm", "Top.SLDASM", top_components
    )

    # depth 1: only the top-level assembly's own pass is unconditional;
    # the sub-assembly component itself is beyond the budget.
    result = await adapter.list_features(include_suppressed=False, max_assembly_depth=1)

    names = [row["name"] for row in result.data]
    assert "SubAssem-1" in names
    assert "Mate2" not in names
    assert "Boss-Extrude1" not in names

    descriptor = next(row for row in result.data if row["name"] == "SubAssem-1")
    assert descriptor["type"] == "Component"
    assert descriptor["component"] == "SubAssem-1"
    assert descriptor["component_path"] == os.path.abspath("C:\\mock\\SubAssem.sldasm")


@pytest.mark.asyncio
async def test_assembly_with_no_components_returns_only_own_features(
    monkeypatch,
) -> None:
    """GetComponents() returning an empty list yields no component rows."""
    adapter = _build_adapter(monkeypatch)
    adapter.currentModel = _assembly_doc(
        "C:\\mock\\Empty.sldasm", "Empty.SLDASM", [], _Feature("Mate1", "Mate")
    )

    result = await adapter.list_features(include_suppressed=False)

    assert result.is_success
    assert [row["name"] for row in result.data] == ["Mate1"]


@pytest.mark.asyncio
async def test_unresolvable_component_does_not_fail_the_call(monkeypatch) -> None:
    """A component that can't be resolved yields one UnresolvedComponent row."""
    adapter = _build_adapter(monkeypatch)

    part_a = _part_doc(
        "C:\\mock\\PartA.sldprt", "PartA.SLDPRT", _Feature("Boss-Extrude1", "Boss")
    )
    components = [
        _component("PartA-1", part_a),
        _component("MissingPart-1", None),
    ]
    adapter.currentModel = _assembly_doc(
        "C:\\mock\\Assem1.sldasm", "Assem1.SLDASM", components
    )

    result = await adapter.list_features(include_suppressed=False)

    assert result.is_success
    by_name = {row["name"]: row for row in result.data}
    assert by_name["Boss-Extrude1"]["component"] == "PartA-1"
    assert by_name["MissingPart-1"]["type"] == "UnresolvedComponent"
    assert by_name["MissingPart-1"]["component"] == "MissingPart-1"
