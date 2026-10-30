"""Tests for the pywin32 adapter's get_model_geometry_summary (COM fakes)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.adapters.solidworks.io import (
    _box_from_metres,
    _byref_double,
)


def _build_adapter(monkeypatch) -> PyWin32Adapter:
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
    monkeypatch.setattr(
        "solidworks_mcp.adapters.pywin32_adapter._ComSessionCoordinator",
        lambda _adapter: SimpleNamespace(),
        raising=False,
    )
    # Bodies come back inside an array; wrapping them is the identity here.
    monkeypatch.setattr(
        "solidworks_mcp.adapters.solidworks.io._dynamic",
        SimpleNamespace(Dispatch=lambda obj: obj),
    )
    return PyWin32Adapter({})


class _Body:
    """An axis-aligned box body answering GetExtremePoint like SolidWorks."""

    def __init__(self, low, high, *, fails: bool = False) -> None:
        self.low, self.high, self.fails = low, high, fails

    def GetExtremePoint(self, dx, dy, dz, ox, oy, oz):  # noqa: N802
        if self.fails:
            raise RuntimeError("Type mismatch")
        for axis, (d, out) in enumerate(zip((dx, dy, dz), (ox, oy, oz), strict=True)):
            out.value = self.high[axis] if d > 0 else self.low[axis]
        return True


class _Model:
    """A document that records any call that would disturb the user."""

    def __init__(self, doc_type: int, volume_m3: float | None = 5e-5) -> None:
        self.doc_type = doc_type
        self.forbidden: list[str] = []
        props = None if volume_m3 is None else SimpleNamespace(Volume=volume_m3)
        self.Extension = SimpleNamespace(CreateMassProperty=lambda: props)
        self.bodies: object = []
        self.part_box: object = None
        self.assembly_box: object = None
        self.components: list[object] = []
        self.first_feature: object = None

    def GetType(self):  # noqa: N802
        return self.doc_type

    def ForceRebuild3(self, *_args):  # noqa: N802
        self.forbidden.append("ForceRebuild3")

    def ClearSelection2(self, *_args):  # noqa: N802
        self.forbidden.append("ClearSelection2")

    def GetBodies2(self, _body_type, _visible_only):  # noqa: N802
        return self.bodies

    def GetPartBox(self, _no_update):  # noqa: N802
        return self.part_box

    def GetBox(self, _options):  # noqa: N802
        return self.assembly_box

    def GetComponents(self, _top_level_only):  # noqa: N802
        return self.components

    def FirstFeature(self):  # noqa: N802
        return self.first_feature


class _Feature:
    """A feature-tree node with optional sub-features."""

    def __init__(self, kind: str, *, children=(), suppressed: bool = False) -> None:
        self.kind = kind
        self.children = list(children)
        self.suppressed = suppressed
        self.next: _Feature | None = None
        self.next_sub: _Feature | None = None
        for current, following in zip(self.children, self.children[1:], strict=False):
            current.next_sub = following

    def GetTypeName2(self):  # noqa: N802
        return self.kind

    def GetNextFeature(self):  # noqa: N802
        return self.next

    def GetFirstSubFeature(self):  # noqa: N802
        return self.children[0] if self.children else None

    def GetNextSubFeature(self):  # noqa: N802
        return self.next_sub

    def IsSuppressed(self):  # noqa: N802
        return self.suppressed


def _chain(*features: _Feature) -> _Feature:
    for current, following in zip(features, features[1:], strict=False):
        current.next = following
    return features[0]


@pytest.mark.asyncio
async def test_part_uses_extreme_points_and_reads_bodies_and_volume(
    monkeypatch,
) -> None:
    adapter = _build_adapter(monkeypatch)
    model = _Model(1)
    model.bodies = [_Body((0.0, 0.0, 0.0), (0.1, 0.05, 0.01))]
    model.part_box = [-1.0, -1.0, -1.0, 1.0, 1.0, 1.0]  # loose; must not be used
    adapter.currentModel = model

    result = await adapter.get_model_geometry_summary()

    assert result.is_success, result.error
    data = result.data
    assert data["document_type"] == "part"
    assert data["solid_body_count"] == 1
    assert data["volume_mm3"] == pytest.approx(50000.0)
    assert data["bounding_box_method"] == "extreme_points"
    assert data["bounding_box_mm"]["size"] == pytest.approx([100.0, 50.0, 10.0])
    assert "component_count" not in data
    assert model.forbidden == []


@pytest.mark.asyncio
async def test_multiple_bodies_combine_into_one_box(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    model = _Model(1)
    model.bodies = [
        _Body((0.0, 0.0, 0.0), (0.01, 0.01, 0.01)),
        _Body((0.02, -0.01, 0.0), (0.03, 0.0, 0.005)),
    ]
    adapter.currentModel = model

    result = await adapter.get_model_geometry_summary()

    assert result.data["solid_body_count"] == 2
    assert result.data["bounding_box_mm"]["min"] == pytest.approx([0.0, -10.0, 0.0])
    assert result.data["bounding_box_mm"]["max"] == pytest.approx([30.0, 10.0, 10.0])


@pytest.mark.asyncio
async def test_extreme_point_failure_falls_back_to_part_box(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    model = _Model(1)
    model.bodies = (_Body((0, 0, 0), (1, 1, 1), fails=True),)
    model.part_box = (0.0, 0.0, 0.0, 0.02, 0.02, 0.04)
    adapter.currentModel = model

    result = await adapter.get_model_geometry_summary()

    assert result.data["bounding_box_method"] == "part_box"
    assert result.data["bounding_box_mm"]["size"] == pytest.approx([20.0, 20.0, 40.0])


@pytest.mark.asyncio
async def test_empty_part_reports_zero_bodies_and_no_box(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    model = _Model(1, volume_m3=None)
    model.bodies = None
    adapter.currentModel = model

    result = await adapter.get_model_geometry_summary()

    assert result.is_success
    assert result.data["solid_body_count"] is None
    assert result.data["bounding_box_mm"] is None
    assert result.data["bounding_box_method"] is None
    assert result.data["volume_mm3"] is None


@pytest.mark.asyncio
async def test_non_numeric_volume_is_reported_unknown(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    model = _Model(1)
    model.Extension = SimpleNamespace(
        CreateMassProperty=lambda: SimpleNamespace(Volume=None)
    )
    adapter.currentModel = model

    result = await adapter.get_model_geometry_summary()

    assert result.data["volume_mm3"] is None


@pytest.mark.asyncio
async def test_single_body_not_in_an_array_is_counted(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    model = _Model(1)
    model.bodies = _Body((0, 0, 0), (0.001, 0.001, 0.001))
    adapter.currentModel = model

    result = await adapter.get_model_geometry_summary()

    assert result.data["solid_body_count"] == 1


@pytest.mark.asyncio
async def test_assembly_counts_components_and_mates(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    model = _Model(2)
    model.assembly_box = [0.0, 0.0, 0.0, 0.12, 0.08, 0.06]
    model.components = [SimpleNamespace(Name2="Base-1"), SimpleNamespace(Name2="Pin-1")]
    mates = _Feature(
        "MateGroup",
        children=[
            _Feature("MateCoincident"),
            _Feature("MateConcentric", suppressed=True),
            _Feature("FtrFolder", children=[_Feature("MateDistanceDim")]),
            _Feature("Reference"),
        ],
    )
    model.first_feature = _chain(
        _Feature("OriginProfileFeature"), _Feature("RefPlane"), mates
    )
    adapter.currentModel = model

    result = await adapter.get_model_geometry_summary()

    data = result.data
    assert data["document_type"] == "assembly"
    assert data["component_count"] == 2
    assert data["mate_count"] == 2  # coincident + the one in the folder
    assert data["solid_body_count"] is None
    assert data["bounding_box_method"] == "assembly_box"
    assert data["bounding_box_mm"]["size"] == pytest.approx([120.0, 80.0, 60.0])
    assert model.forbidden == []


@pytest.mark.asyncio
async def test_assembly_without_mate_group_has_zero_mates(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    model = _Model(2)
    model.first_feature = _chain(_Feature("OriginProfileFeature"))
    adapter.currentModel = model

    result = await adapter.get_model_geometry_summary()

    assert result.data["mate_count"] == 0
    assert result.data["bounding_box_mm"] is None


@pytest.mark.asyncio
async def test_unreadable_feature_tree_reports_unknown_mates(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    adapter.currentModel = _Model(2)

    result = await adapter.get_model_geometry_summary()

    assert result.data["mate_count"] is None


@pytest.mark.asyncio
async def test_no_active_model_is_an_error(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    adapter.currentModel = None

    result = await adapter.get_model_geometry_summary()

    assert result.is_error
    assert "No active model" in (result.error or "")


@pytest.mark.asyncio
async def test_drawing_is_an_error(monkeypatch) -> None:
    adapter = _build_adapter(monkeypatch)
    adapter.currentModel = MagicMock()
    adapter.currentModel.GetType.return_value = 3

    result = await adapter.get_model_geometry_summary()

    assert result.is_error
    assert "needs an active part or assembly" in (result.error or "")


def test_box_from_metres_rejects_non_boxes() -> None:
    assert _box_from_metres(None, "part_box") is None
    assert _box_from_metres([0.0, 0.0, 0.0], "part_box") is None
    assert _box_from_metres([0, 0, 0, "x", 0, 0], "part_box") is None


def test_box_from_metres_orders_corners() -> None:
    box = _box_from_metres([0.01, 0.02, 0.03, 0.0, 0.0, 0.0], "assembly_box")

    assert box == {
        "min": [0.0, 0.0, 0.0],
        "max": [10.0, 20.0, 30.0],
        "size": [10.0, 20.0, 30.0],
        "method": "assembly_box",
    }


def test_byref_double_without_pywin32(monkeypatch) -> None:
    monkeypatch.setattr(
        "solidworks_mcp.adapters.solidworks.io.win32com", SimpleNamespace()
    )

    holder = _byref_double()

    assert holder.value == 0.0
