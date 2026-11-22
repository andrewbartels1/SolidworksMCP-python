"""Tests for the assembly-depth mixin, against a fake assembly that keeps state."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import assembly
from solidworks_mcp.adapters.solidworks.assembly import SolidWorksAssemblyMixin


def _values(array: Any) -> list[Any]:
    """The items of a COM array, whether a VARIANT or a plain tuple."""
    return list(getattr(array, "value", array))


class _Component:
    def __init__(self, name: str, path: str, selectable: bool = True) -> None:
        self.Name2 = name
        self.path = path
        self.Visible = 1
        self._selectable = selectable

    def Select4(self, _append: bool, data: Any, _callout: bool) -> bool:
        self.selected_mark = data.Mark
        self.marks = [*getattr(self, "marks", []), data.Mark]
        return self._selectable

    def GetPathName(self) -> str:
        return self.path


class _Assembly:
    """An open assembly: components, exploded views, a box that grows."""

    def __init__(self) -> None:
        self.components = {
            "base-1": _Component("base-1", "C:/p/base.sldprt"),
            "pin-1": _Component("pin-1", "C:/p/pin30.sldprt"),
        }
        self.views: list[str] = []
        self.exploded = False
        self.lift = 0.0
        self.calls: list[tuple[Any, ...]] = []
        self.known = {
            "Top Plane",
            "Right Plane",
            "Front Plane",
            "Axis1",
            "Drawing View1",
        }
        self.step_result: Any = object()
        self.feature_result: Any = SimpleNamespace(Name="LocalLPattern1")
        self.pattern_extra = 0
        self.auto_ok = True
        self.replace_ok = True
        self.SelectionManager = SimpleNamespace(
            CreateSelectData=lambda: SimpleNamespace(Mark=None),
            GetSelectedObject6=lambda _i, _m: "selected-object",
        )
        self.Extension = SimpleNamespace(SelectByID2=self._select)
        self.FeatureManager = SimpleNamespace(
            CreateDefinition=lambda kind: SimpleNamespace(kind=kind),
            CreateFeature=self._create_feature,
        )

    # IModelDoc2 / IAssemblyDoc
    def ClearSelection2(self, _all: bool) -> bool:
        for component in self.components.values():
            component.__dict__.pop("selected_mark", None)
        self.selected_named: dict[int, str] = {}
        return True

    def _select(self, name: str, kind: str, *args: Any) -> bool:
        self.calls.append(("SelectByID2", name, kind, args[4]))
        if name in self.known:
            self.selected_named = {**getattr(self, "selected_named", {}), args[4]: name}
        return name in self.known

    def GetBox(self, _options: int) -> tuple[float, ...]:
        height = 0.038 + (self.lift if self.exploded else 0.0)
        return (0.0, 0.0, 0.0, 0.12, height, 0.06)

    def AutoExplode(self) -> bool:
        if self.auto_ok:
            self.views.append("ExplView1")
            self.lift = 0.02
        return self.auto_ok

    def GetExplodedViewNames(self) -> tuple[str, ...]:
        return tuple(self.views)

    def CreateExplodedView(self) -> bool:
        self.views.append("ExplView1")
        return True

    def ShowExploded2(self, show: bool, name: str) -> bool:
        self.calls.append(("ShowExploded2", show, name))
        self.exploded = show
        return True

    def IsExploded(self) -> bool:
        return self.exploded

    def GetActiveConfiguration(self) -> Any:
        def add_step(distance: float, *args: Any) -> Any:
            self.calls.append(("AddExplodeStep2", distance, args[0], args[1]))
            if self.step_result is not None:
                self.lift += distance
            return self.step_result

        return SimpleNamespace(AddExplodeStep2=add_step)

    def _create_feature(self, data: Any) -> Any:
        """Pattern what's selected, as SolidWorks does: seeds 1, axis 2."""
        axis = getattr(self, "selected_named", {}).get(2)
        self.calls.append(("CreateFeature", data.kind, axis))
        if self.feature_result is None or axis is None:
            return None
        count = getattr(data, "D1TotalInstances", None) or data.TotalInstances
        seeds = [
            c
            for c in list(self.components.values())
            if getattr(c, "selected_mark", None) == 1
        ]
        for seed in seeds:
            for copy in range(2, count + 1 + self.pattern_extra):
                name = f"{seed.Name2.split('-')[0]}-{copy}"
                self.components[name] = _Component(name, seed.path)
        return self.feature_result

    def MirrorComponents3(self, plane: Any, comps: Any, orient: Any, *rest: Any) -> Any:
        self.calls.append(("MirrorComponents3", plane, _values(orient)))
        for comp in _values(comps):
            name = f"{comp.Name2.split('-')[0]}-mirror"
            self.components[name] = _Component(name, comp.path)
        return None

    def ReplaceComponents2(
        self, file: str, _cfg: str, every: bool, _use: int, _mates: bool
    ) -> bool:
        if self.replace_ok:
            for comp in self.components.values():
                if comp.Name2.startswith("pin"):
                    comp.path = file
                    if not every:
                        break
        return self.replace_ok

    def SetComponentTransparent(self, state: bool) -> bool:
        self.calls.append(("SetComponentTransparent", state))
        return True

    # IDrawingDoc
    def CreateAutoBalloonOptions(self) -> Any:
        return SimpleNamespace()

    def AutoBalloon5(self, options: Any) -> Any:
        self.calls.append(("AutoBalloon5", options.Layout, options.IgnoreMultiple))
        return tuple(SimpleNamespace(GetText=lambda i=i: str(i)) for i in (1, 2, 3))


class _Adapter(SolidWorksAssemblyMixin):
    def __init__(self, doc_type: int = 2) -> None:
        self.currentModel = _Assembly()
        self.doc_type = doc_type

    def _attempt(self, fn: Any, default: Any = None) -> Any:
        try:
            return fn()
        except Exception:
            return default

    def _handle_com_operation(self, _name: str, fn: Any) -> AdapterResult[Any]:
        try:
            return AdapterResult(status=AdapterResultStatus.SUCCESS, data=fn())
        except Exception as exc:
            return AdapterResult(status=AdapterResultStatus.ERROR, error=str(exc))


@pytest.fixture(autouse=True)
def _fake_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the io helpers at the fake assembly."""

    def find(adapter: Any, model: Any, names: list[str]) -> dict[str, Any]:
        missing = [n for n in names if n not in model.components]
        if missing:
            raise Exception(f"Component(s) not found: {', '.join(missing)}.")
        return {n: model.components[n] for n in names}

    monkeypatch.setattr(assembly, "_doc_type", lambda a: a.doc_type)
    monkeypatch.setattr(assembly, "_find_components", find)
    monkeypatch.setattr(assembly, "_component_names", lambda a, m: list(m.components))
    monkeypatch.setattr(
        assembly,
        "_resolve_drawing_view",
        lambda a, d, name: object() if name == "Drawing View1" else None,
    )
    monkeypatch.setattr(assembly, "_view_names", lambda a, d: ["Drawing View1"])


@pytest.mark.asyncio
async def test_an_automatic_explode_is_shown_and_measured() -> None:
    adapter = _Adapter()

    result = await adapter.create_exploded_view()

    assert result.data == {
        "view": "ExplView1",
        "steps": 0,
        "automatic": True,
        "size_before_mm": [120.0, 38.0, 60.0],
        "size_after_mm": [120.0, 58.0, 60.0],
    }


@pytest.mark.asyncio
async def test_explode_steps_select_components_and_the_direction_plane() -> None:
    adapter = _Adapter()

    result = await adapter.create_exploded_view(
        [{"components": ["pin-1"], "direction": "y", "distance": 40.0}]
    )

    model = adapter.currentModel
    assert result.data["size_after_mm"] == [120.0, 78.0, 60.0]
    assert model.components["pin-1"].marks == [1]
    assert ("SelectByID2", "Top Plane", "PLANE", 2) in model.calls
    # Along the Top Plane's normal (index 2), +y; not an in-plane axis.
    assert ("AddExplodeStep2", 0.04, 2, False) in model.calls
    assert model.views == ["ExplView1"]


@pytest.mark.asyncio
async def test_a_refused_step_names_it_and_a_missing_component_fails_first() -> None:
    refused = _Adapter()
    refused.currentModel.step_result = None
    missing = _Adapter()

    step = await refused.create_exploded_view(
        [{"components": ["pin-1"], "direction": "x", "distance": 5.0, "reverse": True}]
    )
    gone = await missing.create_exploded_view(
        [{"components": ["bolt-9"], "direction": "z", "distance": 5.0}]
    )

    assert step.error == "SolidWorks refused explode step 1"
    assert "Component(s) not found: bolt-9" in (gone.error or "")
    assert not any(c[0] == "AddExplodeStep2" for c in missing.currentModel.calls)


@pytest.mark.asyncio
async def test_an_explode_needs_an_assembly_and_can_be_refused() -> None:
    part = await _Adapter(doc_type=1).create_exploded_view()
    adapter = _Adapter()
    adapter.currentModel.auto_ok = False

    refused = await adapter.create_exploded_view()

    assert part.error == "create_exploded_view requires an assembly document"
    assert refused.error == "SolidWorks didn't explode the assembly"


@pytest.mark.asyncio
async def test_collapse_and_explode_again() -> None:
    adapter = _Adapter()
    none = await adapter.set_exploded_view(True)
    await adapter.create_exploded_view()

    collapsed = await adapter.set_exploded_view(False)
    again = await adapter.set_exploded_view(True)
    part = await _Adapter(doc_type=1).set_exploded_view(True)

    assert "No exploded view found" in (none.error or "")
    assert collapsed.data == {
        "view": "ExplView1",
        "exploded": False,
        "size_mm": [120.0, 38.0, 60.0],
    }
    assert again.data["exploded"] is True
    assert part.error == "set_exploded_view requires an assembly document"


@pytest.mark.asyncio
async def test_a_linear_component_pattern() -> None:
    adapter = _Adapter()

    result = await adapter.pattern_components(["pin-1"], "Axis1", 4, spacing=25.0)

    assert result.data == {
        "feature": "LocalLPattern1",
        "components_before": 2,
        "components_after": 5,
        "added": ["pin-2", "pin-3", "pin-4"],
    }
    assert ("CreateFeature", 108, "Axis1") in adapter.currentModel.calls
    assert ("SelectByID2", "Axis1", "AXIS", 2) in adapter.currentModel.calls


@pytest.mark.asyncio
async def test_a_circular_component_pattern_spaces_360_equally() -> None:
    adapter = _Adapter()
    seen: list[Any] = []
    real = adapter.currentModel.FeatureManager.CreateFeature

    def record(data: Any) -> Any:
        seen.append(data)
        return real(data)

    adapter.currentModel.FeatureManager.CreateFeature = record

    result = await adapter.pattern_components(["pin-1"], "Axis1", 3, kind="circular")

    assert result.data["added"] == ["pin-2", "pin-3"]
    assert seen[0].kind == 109
    assert seen[0].EqualSpacing is True
    assert seen[0].Spacing == pytest.approx(2 * math.pi)


@pytest.mark.asyncio
async def test_a_pattern_that_fails_or_adds_the_wrong_count() -> None:
    refused = _Adapter()
    refused.currentModel.feature_result = None
    extra = _Adapter()
    extra.currentModel.pattern_extra = 1
    no_axis = _Adapter()

    failed = await refused.pattern_components(["pin-1"], "Axis1", 2, spacing=5.0)
    wrong = await extra.pattern_components(["pin-1"], "Axis1", 2, spacing=5.0)
    missing = await no_axis.pattern_components(["pin-1"], "Axis9", 2, spacing=5.0)
    part = await _Adapter(doc_type=1).pattern_components(["pin-1"], "A", 2, spacing=1)

    assert failed.error == "SolidWorks refused the component pattern"
    assert wrong.error == "The component pattern added 2 components, not 1"
    assert missing.error == "Axis 'Axis9' not found in the assembly"
    assert "requires an assembly document" in (part.error or "")


@pytest.mark.asyncio
async def test_mirror_adds_one_instance_per_component() -> None:
    adapter = _Adapter()

    result = await adapter.mirror_components(["pin-1"], "Right Plane")
    missing = await adapter.mirror_components(["pin-1"], "Plane9")
    part = await _Adapter(doc_type=1).mirror_components(["pin-1"], "Right Plane")

    assert result.data == {"plane": "Right Plane", "added": ["pin-mirror"]}
    assert ("MirrorComponents3", "selected-object", [0]) in adapter.currentModel.calls
    assert missing.error == "Plane 'Plane9' not found in the assembly"
    assert "requires an assembly document" in (part.error or "")


@pytest.mark.asyncio
async def test_a_mirror_that_adds_nothing_is_an_error() -> None:
    adapter = _Adapter()
    adapter.currentModel.MirrorComponents3 = lambda *a: None

    result = await adapter.mirror_components(["pin-1"], "Right Plane")

    assert result.error == "Mirroring about Right Plane added 0 components, not 1"


@pytest.mark.asyncio
async def test_replace_every_instance_reads_the_files_back(tmp_path: Any) -> None:
    longer = tmp_path / "pin45.sldprt"
    longer.write_text("part")
    adapter = _Adapter()
    adapter.currentModel.components["pin-2"] = _Component("pin-2", "C:/p/pin30.sldprt")

    result = await adapter.replace_component("pin-1", str(longer), all_instances=True)

    assert result.data["replaced"] == {"pin-1": str(longer), "pin-2": str(longer)}
    assert result.data["components_after"] == ["base-1", "pin-1", "pin-2"]


@pytest.mark.asyncio
async def test_replace_needs_a_file_and_an_assembly_and_can_be_refused(
    tmp_path: Any,
) -> None:
    real = tmp_path / "pin45.sldprt"
    real.write_text("part")
    refused = _Adapter()
    refused.currentModel.replace_ok = False
    unchanged = _Adapter()
    unchanged.currentModel.ReplaceComponents2 = lambda *a: True

    no_file = await _Adapter().replace_component("pin-1", str(tmp_path / "x.sldprt"))
    part = await _Adapter(doc_type=1).replace_component("pin-1", str(real))
    failed = await refused.replace_component("pin-1", str(real))
    stale = await unchanged.replace_component("pin-1", str(real))

    assert "No file at" in (no_file.error or "")
    assert "requires an assembly document" in (part.error or "")
    assert failed.error == "SolidWorks refused to replace pin-1"
    assert stale.error == "pin-1 still uses C:/p/pin30.sldprt"


@pytest.mark.asyncio
async def test_hide_show_and_transparent() -> None:
    adapter = _Adapter()
    pin = adapter.currentModel.components["pin-1"]

    hidden = await adapter.set_component_appearance("pin-1", visible=False)
    shown = await adapter.set_component_appearance(
        "pin-1", visible=True, transparent=True
    )

    assert hidden.data == {"visible": False, "transparent": None}
    assert shown.data == {"visible": True, "transparent": True}
    assert pin.Visible == 1
    assert ("SetComponentTransparent", True) in adapter.currentModel.calls


@pytest.mark.asyncio
async def test_a_visibility_solidworks_ignores_and_no_assembly() -> None:
    adapter = _Adapter()

    class _Stuck(_Component):
        @property
        def Visible(self) -> int:
            return 1

        @Visible.setter
        def Visible(self, _value: int) -> None:
            pass

    adapter.currentModel.components["pin-1"] = _Stuck("pin-1", "C:/p/pin30.sldprt")
    stuck = await adapter.set_component_appearance("pin-1", visible=False)
    part = await _Adapter(doc_type=1).set_component_appearance("pin-1", visible=False)

    assert stuck.error == "pin-1 is still shown"
    assert part.error == "set_component_state requires an assembly document"


@pytest.mark.asyncio
async def test_a_component_that_wont_select_is_an_error(tmp_path: Any) -> None:
    adapter = _Adapter()
    adapter.currentModel.components["pin-1"] = _Component(
        "pin-1", "x", selectable=False
    )

    result = await adapter.set_component_appearance("pin-1", transparent=True)

    assert result.error == "Couldn't select pin-1"


@pytest.mark.asyncio
async def test_balloons_one_per_part() -> None:
    adapter = _Adapter(doc_type=3)

    result = await adapter.add_balloons("Drawing View1", "circle")

    assert result.data == {
        "view": "Drawing View1",
        "layout": "circle",
        "count": 3,
        "items": ["1", "2", "3"],
    }
    assert ("AutoBalloon5", 2, True) in adapter.currentModel.calls


@pytest.mark.asyncio
async def test_balloons_need_a_drawing_a_view_and_some_parts() -> None:
    adapter = _Adapter(doc_type=3)
    empty = _Adapter(doc_type=3)
    empty.currentModel.AutoBalloon5 = lambda _o: ()

    part = await _Adapter(doc_type=2).add_balloons("Drawing View1")
    missing = await adapter.add_balloons("Drawing View9")
    none = await empty.add_balloons("Drawing View1")

    assert part.error == "add_balloons requires a drawing document"
    assert missing.error == "No view named 'Drawing View9'. Views: Drawing View1"
    assert none.error == "SolidWorks added no balloons to Drawing View1"


def test_the_box_is_none_when_solidworks_gives_none() -> None:
    adapter = _Adapter()
    adapter.currentModel.GetBox = lambda _o: None

    assert assembly._box_size(adapter, adapter.currentModel) is None


def test_the_adapter_helper_returns_its_object() -> None:
    marker = object()

    assert SolidWorksAssemblyMixin._adapter(marker) is marker
