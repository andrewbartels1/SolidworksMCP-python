"""Fake SolidWorks COM objects for the appearance and reference-extras tests.

Shaped like the calls the probes of 2026-11-28 measured (design.md of the
``appearance-and-reference-tools`` change): colours as nine values, a face
picked with ``SelectByID2`` and read with ``GetSelectedObject6``, section
properties of the selection, a transform's ``ArrayData``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks.appearance import SolidWorksAppearanceMixin
from solidworks_mcp.adapters.solidworks.bodies import SolidWorksBodiesMixin
from solidworks_mcp.adapters.solidworks.reference_extras import (
    SolidWorksReferenceExtrasMixin,
)

#: A 40 mm square face at y = 10, as GetSectionProperties2 gave it.
SQUARE_SECTION = (
    [0.0, 0.0016, 0.0, 0.01, 0.0]
    + [2.1333e-7, 4.2667e-7, 2.1333e-7, 0.0, 0.0, 0.0, 4.2667e-7, 0.0]
    + [2.1333e-7, 2.1333e-7]
    + [0.0] * 9
)
NO_COLOUR = [-1.0] * 9


class Coloured:
    """A feature, body or face holding its own colour (None when it has none)."""

    def __init__(self, name: str = "", values: Any = None) -> None:
        self.Name = name
        self.values = values
        self.removed = 0

    # IFace2 / IModelDoc2 style property.
    @property
    def MaterialPropertyValues(self) -> Any:
        return self.values

    @MaterialPropertyValues.setter
    def MaterialPropertyValues(self, values: Any) -> None:
        self.values = list(values)

    # IBody2 style property.
    @property
    def MaterialPropertyValues2(self) -> Any:
        return self.values

    @MaterialPropertyValues2.setter
    def MaterialPropertyValues2(self, values: Any) -> None:
        self.values = list(values)

    # IFeature style methods.
    def GetMaterialPropertyValues2(self, option: int, names: Any) -> Any:
        return self.values if self.values is not None else NO_COLOUR

    def SetMaterialPropertyValues2(self, values: Any, option: int, names: Any) -> None:
        self.values = list(values)

    def RemoveMaterialProperty2(self, option: int, names: Any) -> bool:
        self.values, self.removed = None, self.removed + 1
        return True

    def RemoveMaterialProperty(self, option: int, names: Any) -> bool:
        return self.RemoveMaterialProperty2(option, names)


class Body(Coloured):
    """IBody2: a 40 x 10 x 40 mm block's volume and box, and its colour."""

    def __init__(self, name: str = "Boss-Extrude1") -> None:
        super().__init__(name)

    def GetMassProperties(self, density: float) -> tuple[float, ...]:
        return (0.0, 0.0, 0.0, 16000 / 1e9, 0.0, 0.0)

    def GetBodyBox(self) -> tuple[float, ...]:
        return (-0.02, 0.0, -0.02, 0.02, 0.01, 0.02)


class Face(Coloured):
    """IFace2 with its feature and body."""

    def __init__(self, feature: Coloured | None, body: Body | None) -> None:
        super().__init__("face")
        self.feature, self.body = feature, body

    def GetFeature(self) -> Any:
        return self.feature

    def GetBody(self) -> Any:
        return self.body


class TreeFeature:
    """IFeature as the tree walk reads it."""

    def __init__(self, name: str, type_name: str, nxt: Any = None) -> None:
        self.Name, self.type_name, self.nxt = name, type_name, nxt

    def GetTypeName2(self) -> str:
        return self.type_name

    def GetNextFeature(self) -> Any:
        return self.nxt


class Model(Coloured):
    """IModelDoc2 (a part) with its extension, managers and one block."""

    def __init__(self, bodies: list[Body] | None = None) -> None:
        super().__init__("Part1", [0.894118] * 3 + [1.0, 1.0, 0.5, 0.3125, 0.0, 0.0])
        self.bodies = [Body()] if bodies is None else bodies
        self.feature = Coloured("Boss-Extrude1")
        self.face = Face(self.feature, self.bodies[0] if self.bodies else None)
        self.faces: dict[tuple[float, float, float], Face] = {
            (0.0, 0.01, 0.0): self.face
        }
        self.selected: Any = None
        self.section: Any = SQUARE_SECTION
        self.inserted: list[tuple[str, tuple[Any, ...]]] = []
        self.tree: Any = TreeFeature("Origin", "OriginProfileFeature")
        self.made: dict[str, Any] = {
            "coordinate": SimpleNamespace(Name="Coordinate System1"),
            "com": SimpleNamespace(Name="Center of Mass"),
            "box": SimpleNamespace(Name="Bounding Box"),
        }
        self.point: Any = object()
        self.last_sketch = SimpleNamespace(Name="3DSketch1")
        self.transform = SimpleNamespace(
            ArrayData=[1, 0, 0, 0, 1, 0, 0, 0, 1, 0.02, 0.01, 0.02, 1, 0, 0, 0]
        )
        self.centre: Any = (0.0, 0.005, 0.0)
        self.Extension = SimpleNamespace(
            SelectByID2=self._select,
            GetSectionProperties2=lambda sections: self.section,
            CreateMassProperty=lambda: SimpleNamespace(CenterOfMass=self.centre),
            GetCoordinateSystemTransformByName=lambda name: self.transform,
        )
        self.SelectionManager = SimpleNamespace(
            GetSelectedObject6=lambda index, mark: self.selected
        )
        self.FeatureManager = SimpleNamespace(
            InsertCoordinateSystem=lambda *a: self._insert("coordinate", a),
            InsertCenterOfMass=lambda: self._insert("com", ()),
            InsertGlobalBoundingBox=lambda *a: self._insert("box", a),
        )
        self.SketchManager = SimpleNamespace(
            Insert3DSketch=lambda update: None,
            CreatePoint=lambda x, y, z: self.point,
        )

    def _select(
        self, name: str, kind: str, x: float, y: float, z: float, *rest: Any
    ) -> bool:
        self.inserted.append(("select", (name, kind, x, y, z, *rest)))
        if kind == "FACE":
            self.selected = self.faces.get((round(x, 6), round(y, 6), round(z, 6)))
            return self.selected is not None
        return True

    def _insert(self, what: str, args: tuple[Any, ...]) -> Any:
        self.inserted.append((what, args))
        return self.made[what]

    def GetType(self) -> int:
        return 1

    def GetBodies2(self, kind: int, visible_only: bool) -> Any:
        return tuple(self.bodies) or None

    def FeatureByName(self, name: str) -> Any:
        return self.feature if name == "Boss-Extrude1" else None

    def FeatureByPositionReverse(self, index: int) -> Any:
        return self.last_sketch

    def FirstFeature(self) -> Any:
        return self.tree

    def ForceRebuild3(self, top_only: bool) -> bool:
        return True

    def ClearSelection2(self, everything: bool) -> None:
        self.selected = None

    def GraphicsRedraw2(self) -> None:
        return None


class Harness(
    SolidWorksAppearanceMixin, SolidWorksReferenceExtrasMixin, SolidWorksBodiesMixin
):
    """The three mixins plus the PyWin32Adapter members they use."""

    def __init__(self, model: Any) -> None:
        self.currentModel = model

    def _attempt(self, operation: Any, default: Any = None) -> Any:
        try:
            return operation()
        except Exception:
            return default

    def _get_attr_or_call(self, obj: Any, attr_name: str) -> Any:
        attr = getattr(obj, attr_name, None)
        return attr() if callable(attr) else attr

    def _handle_com_operation(self, name: str, operation: Any) -> AdapterResult[Any]:
        try:
            data = operation()
        except Exception as e:  # mirrors PyWin32Adapter._handle_com_operation
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=data)
