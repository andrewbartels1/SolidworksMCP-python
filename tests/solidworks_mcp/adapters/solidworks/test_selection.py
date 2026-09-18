"""Tests for the SolidWorksSelectionMixin."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks.selection import SolidWorksSelectionMixin


class _SelectionHarness(SolidWorksSelectionMixin):
    """Minimal harness to exercise the mixin methods."""

    def __init__(self, *, has_model: bool, swApp: object | None = None) -> None:
        self.currentModel = object() if has_model else None
        self.swApp = swApp
        self._feature_selector = SimpleNamespace(
            list_features=lambda _include, _depth=2: [{"name": "Feat1"}],
            select_feature=lambda _name: {"selected": True},
        )

    def _handle_com_operation(self, _name, operation, *args):
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=operation(*args))

    def _attempt(self, operation, default=None):
        try:
            return operation()
        except Exception:
            return default


@pytest.mark.asyncio
async def test_list_features_requires_active_model() -> None:
    """list_features should error when no model is active."""
    # Validate the error branch when currentModel is missing.
    harness = _SelectionHarness(has_model=False)
    result = await harness.list_features()
    assert result.status == AdapterResultStatus.ERROR


@pytest.mark.asyncio
async def test_select_feature_requires_active_model() -> None:
    """select_feature should error when no model is active."""
    # Validate the error branch when currentModel is missing.
    harness = _SelectionHarness(has_model=False)
    result = await harness.select_feature("Feat1")
    assert result.status == AdapterResultStatus.ERROR


@pytest.mark.asyncio
async def test_list_and_select_feature_success() -> None:
    """list_features/select_feature should call the selector when model exists."""
    # Exercise the success path when currentModel is set.
    harness = _SelectionHarness(has_model=True)
    list_result = await harness.list_features()
    select_result = await harness.select_feature("Feat1")
    assert list_result.is_success
    assert list_result.data == [{"name": "Feat1"}]
    assert select_result.is_success
    assert select_result.data == {"selected": True}


class _FakeFace:
    """Stand-in for IFace2 covering the fields get_selected_entities reads."""

    def _FlagAsMethod(self, _name) -> None:  # noqa: N802 - matches pywin32's API
        pass

    def GetBox(self):
        # (xmin, ymin, zmin, xmax, ymax, zmax) in meters
        return (0.0, 0.0, 0.0, 0.03, 0.03, 0.0)

    def GetArea(self):
        return 0.0009  # m^2 -> 900 mm^2

    @property
    def Normal(self):
        return (0.0, 0.0, 1.0)


class _FakeVertex:
    def __init__(self, point):
        self._point = point

    def _FlagAsMethod(self, _name) -> None:  # noqa: N802
        pass

    def GetPoint(self):
        return self._point


class _FakeEdge:
    """Stand-in for IEdge covering the fields get_selected_entities reads."""

    def _FlagAsMethod(self, _name) -> None:  # noqa: N802
        pass

    def GetStartVertex(self):
        return _FakeVertex((0.0, 0.0, -0.015))

    def GetEndVertex(self):
        return _FakeVertex((0.03, 0.0, -0.015))


class _FakeSelectionManager:
    def __init__(self, objects: list[tuple[int, object]]) -> None:
        self._objects = objects

    def _FlagAsMethod(self, _name) -> None:  # noqa: N802
        pass

    def GetSelectedObjectCount2(self, _mark):
        return len(self._objects)

    def GetSelectedObjectType3(self, index, _mark):
        return self._objects[index - 1][0]

    def GetSelectedObject6(self, index, _mark):
        return self._objects[index - 1][1]


@pytest.mark.asyncio
async def test_get_selected_entities_requires_active_model() -> None:
    """get_selected_entities should error when no model is active and swApp has no ActiveDoc."""
    harness = _SelectionHarness(has_model=False, swApp=None)
    result = await harness.get_selected_entities()
    assert result.status == AdapterResultStatus.ERROR
    assert "No active model" in (result.error or "")


@pytest.mark.asyncio
async def test_get_selected_entities_describes_face_and_edge() -> None:
    """A selected FACE and EDGE should each be described with their own fields."""
    sel_mgr = _FakeSelectionManager(
        [(2, _FakeFace()), (3, _FakeEdge())]  # swSelFACES=2, swSelEDGES=3
    )
    model = SimpleNamespace(SelectionManager=sel_mgr)
    harness = _SelectionHarness(has_model=True)
    harness.currentModel = model
    harness.swApp = SimpleNamespace(ActiveDoc=None)

    result = await harness.get_selected_entities()

    assert result.is_success
    entities = result.data
    assert len(entities) == 2

    face = entities[0]
    assert face["type"] == "FACE"
    assert face["center_mm"] == [15.0, 15.0, 0.0]
    assert face["area_mm2"] == pytest.approx(900.0)
    assert face["normal"] == [0.0, 0.0, 1.0]

    edge = entities[1]
    assert edge["type"] == "EDGE"
    assert edge["start_mm"] == [0.0, 0.0, -15.0]
    assert edge["end_mm"] == [30.0, 0.0, -15.0]
    assert edge["length_mm"] == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_get_selected_entities_refreshes_current_model_from_active_doc() -> None:
    """The live UI selection lives on swApp.ActiveDoc, which may differ from
    whatever this adapter instance last tracked as currentModel -- the
    method must prefer ActiveDoc, mirroring list_features's behavior."""
    sel_mgr = _FakeSelectionManager([])
    active_doc = SimpleNamespace(SelectionManager=sel_mgr)
    harness = _SelectionHarness(has_model=True)
    harness.swApp = SimpleNamespace(ActiveDoc=active_doc)

    result = await harness.get_selected_entities()

    assert result.is_success
    assert result.data == []
    assert harness.currentModel is active_doc
