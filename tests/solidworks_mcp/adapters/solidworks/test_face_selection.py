"""Tests for face resolution + edge multi-selection (select_face_edges, #106).

Fake COM objects model a 60 x 40 x 10 mm block (Front-sketched, extruded +Z)
with a 4 mm radius through-hole at (30, 20): six planar faces plus the
cylindrical hole wall, whose top/bottom rims are full circles (no vertices).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus
from solidworks_mcp.adapters.solidworks import face_selection as fs
from solidworks_mcp.adapters.solidworks.selection import SolidWorksSelectionMixin

# ---- fakes -----------------------------------------------------------------


class _Curve:
    def __init__(self, kind: str, params: list[float] | None = None) -> None:
        self._kind = kind
        self.CircleParams = params

    def IsCircle(self) -> bool:  # noqa: N802
        return self._kind == "circle"

    def IsLine(self) -> bool:  # noqa: N802
        return self._kind == "line"


class _Vertex:
    def __init__(self, p_mm: tuple[float, float, float]) -> None:
        self._p = [c / 1000 for c in p_mm]

    def GetPoint(self) -> list[float]:  # noqa: N802
        return self._p


class _Edge:
    def __init__(self, curve: _Curve, a=None, b=None, select_ok=True) -> None:  # noqa: ANN001
        self._curve, self._a, self._b, self._ok = curve, a, b, select_ok
        self.selected_with: list[tuple[bool, Any]] = []

    def GetCurve(self) -> _Curve:  # noqa: N802
        return self._curve

    def GetStartVertex(self):  # noqa: ANN201, N802
        return _Vertex(self._a) if self._a else None

    def GetEndVertex(self):  # noqa: ANN201, N802
        return _Vertex(self._b) if self._b else None

    def Select4(self, append: bool, data: Any) -> bool:  # noqa: N802
        self.selected_with.append((append, data))
        return self._ok


def _line(a, b, ok=True) -> _Edge:  # noqa: ANN001
    return _Edge(_Curve("line"), a, b, ok)


def _rim(z_mm: float) -> _Edge:
    return _Edge(_Curve("circle", [0.03, 0.02, z_mm / 1000, 0, 0, 1, 0.004]))


class _Face:
    def __init__(self, normal, box_mm, area_mm2, edges, plane_axis=None) -> None:  # noqa: ANN001
        self.Normal = list(normal)
        self._box = [c / 1000 for c in box_mm]
        self._area = area_mm2 / 1e6
        self._edges = edges
        self._axis = plane_axis  # (index, value_m) for planar faces

    def GetBox(self) -> list[float]:  # noqa: N802
        return self._box

    def GetArea(self) -> float:  # noqa: N802
        return self._area

    def GetEdges(self) -> list[_Edge]:  # noqa: N802
        return self._edges

    def GetClosestPointOn(self, x: float, y: float, z: float) -> list[float]:  # noqa: N802
        # Clamp to the face's box: exact for these axis-aligned planar faces.
        b = self._box
        p = [min(max(v, b[i]), b[i + 3]) for i, v in enumerate((x, y, z))]
        return [*p, 0.0, 0.0]


def _block() -> tuple[list[_Face], dict[str, list[_Edge]]]:
    top_lines = [
        _line((0, 0, 10), (60, 0, 10)),
        _line((60, 0, 10), (60, 40, 10)),
        _line((60, 40, 10), (0, 40, 10)),
        _line((0, 40, 10), (0, 0, 10)),
    ]
    top_rim, bottom_rim = _rim(10), _rim(0)
    faces = [
        _Face((0, 0, 1), (0, 0, 10, 60, 40, 10), 2349.7, [*top_lines, top_rim]),
        _Face(
            (0, 0, -1),
            (0, 0, 0, 60, 40, 0),
            2349.7,
            [_line((0, 0, 0), (60, 0, 0)), bottom_rim],
        ),
        _Face((-1, 0, 0), (0, 0, 0, 0, 40, 10), 400, [_line((0, 0, 0), (0, 40, 0))]),
        _Face((0, -1, 0), (0, 0, 0, 60, 0, 10), 600, [_line((0, 0, 0), (60, 0, 0))]),
        _Face((1, 0, 0), (60, 0, 0, 60, 40, 10), 400, [_line((60, 0, 0), (60, 40, 0))]),
        _Face((0, 1, 0), (0, 40, 0, 60, 40, 10), 600, [_line((0, 40, 0), (60, 40, 0))]),
        _Face((0, 0, 0), (26, 16, 0, 34, 24, 10), 251.3, [top_rim, bottom_rim]),
    ]
    return faces, {"top": [*top_lines, top_rim]}


_PLANES = {
    "Front Plane": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    "Top Plane": [1, 0, 0, 0, 0, -1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0],
    # Parallel to Front, 5 mm up: cuts through the block, touches no face.
    "Mid Plane": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0.005, 1, 0, 0, 0],
}


class _SelMgr:
    def __init__(self) -> None:
        self.count = 0

    def CreateSelectData(self) -> str:  # noqa: N802
        return "select-data"

    def GetSelectedObjectCount2(self, _mark: int) -> int:  # noqa: N802
        return self.count


def _model(faces: list[_Face], doc_type: int = 1) -> SimpleNamespace:
    sel = _SelMgr()

    def _clear(_all: bool) -> None:
        sel.count = 0

    def _feature_by_name(name: str):  # noqa: ANN202
        data = _PLANES.get(name)
        if data is None:
            return None
        ref = SimpleNamespace(Transform=SimpleNamespace(ArrayData=data))
        return SimpleNamespace(GetSpecificFeature2=lambda: ref)

    body = SimpleNamespace(GetFaces=lambda: faces)
    return SimpleNamespace(
        GetBodies2=lambda _t, _v: [body],
        GetType=lambda: doc_type,
        FeatureByName=_feature_by_name,
        SelectionManager=sel,
        ClearSelection2=_clear,
    )


class _Harness(SolidWorksSelectionMixin):
    def __init__(self, model: Any) -> None:
        self.currentModel = model
        self.swApp = None

    def _handle_com_operation(self, name, operation, *args):  # noqa: ANN001, ANN202
        try:
            return AdapterResult(
                status=AdapterResultStatus.SUCCESS, data=operation(*args)
            )
        except Exception as e:  # noqa: BLE001 - mirror the real adapter
            return AdapterResult(
                status=AdapterResultStatus.ERROR, error=f"Error in {name}: {e}"
            )

    def _attempt(self, operation, default=None):  # noqa: ANN001, ANN202
        try:
            return operation()
        except Exception:  # noqa: BLE001
            return default

    def _get_attr_or_call(self, obj, name):  # noqa: ANN001, ANN202
        value = getattr(obj, name)
        return value() if callable(value) else value


def _count_selected(edges: list[_Edge]) -> int:
    return sum(1 for e in edges if e.selected_with)


# ---- pure helpers ------------------------------------------------------------


@pytest.mark.parametrize(
    ("token", "vec"),
    [
        ("top", (0, 1, 0)),
        ("+Z", (0, 0, 1)),
        (" Front ", (0, 0, 1)),
        ("left", (-1, 0, 0)),
    ],
)
def test_side_vector_tokens_and_aliases(token: str, vec: tuple) -> None:
    """Side tokens are case/space-insensitive and aliases map to SW axes."""
    assert fs.side_vector(token) == vec


def test_side_vector_rejects_unknown() -> None:
    """An unknown token raises ValueError listing the valid ones."""
    with pytest.raises(ValueError, match="Unknown side 'up'"):
        fs.side_vector("up")


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({}, "exactly one"),
        ({"side": "top", "plane": "Front Plane"}, "exactly one"),
        ({"point": [1, 2]}, "[x, y, z]"),
        ({"side": "sideways"}, "Unknown side"),
        ({"side": "top", "edge_type": "spline"}, "edge_type"),
    ],
)
def test_validate_face_query_errors(kwargs: dict, fragment: str) -> None:
    """Invalid combinations produce a descriptive message."""
    args = {"point": None, "side": None, "plane": None, "edge_type": "all"} | kwargs
    assert fragment in (fs.validate_face_query(**args) or "")


def test_validate_face_query_ok() -> None:
    """A single identifier with a valid filter passes."""
    assert fs.validate_face_query([1, 2, 3], None, None, "circular") is None


def test_pick_side_face_prefers_furthest_then_larger() -> None:
    """A stepped top: the higher +Y face wins; ties go to the larger area."""
    low = fs.FaceInfo(0, (0, 1, 0), (0, 0.005, 0, 1, 0.005, 1), 1.0)
    high_small = fs.FaceInfo(1, (0, 1, 0), (0, 0.01, 0, 1, 0.01, 1), 0.5)
    high_big = fs.FaceInfo(2, (0, 1, 0), (0, 0.01, 0, 1, 0.01, 1), 2.0)
    side = fs.FaceInfo(3, (1, 0, 0), (0, 0, 0, 0, 1, 1), 9.0)
    curved = fs.FaceInfo(4, (0, 0, 0), (0, 0, 0, 1, 1, 1), 9.0)
    assert (
        fs.pick_side_face([low, high_small, high_big, side, curved], (0, 1, 0))
        is high_big
    )
    assert fs.pick_side_face([side, curved], (0, 1, 0)) is None


def test_plane_helpers_use_rotated_z_and_translation() -> None:
    """Normal is ArrayData[6:9], origin [9:12]; faces must lie in the plane."""
    origin, normal = fs.plane_from_transform(_PLANES["Top Plane"])
    assert (origin, normal) == ((0, 0, 0), (0, 1, 0))
    on = fs.FaceInfo(0, (0, -1, 0), (0, 0, 0, 1, 0, 1), 1.0)
    off = fs.FaceInfo(1, (0, 1, 0), (0, 0.01, 0, 1, 0.01, 1), 1.0)
    assert fs.faces_on_plane([on, off], origin, normal) == [on]


def test_face_info_describe_in_mm() -> None:
    """describe() reports mm / mm^2 and planarity."""
    face = fs.FaceInfo(0, (0, 0, 1), (0, 0, 0.01, 0.06, 0.04, 0.01), 0.0024)
    assert face.describe() == {
        "index": 0,
        "center_mm": [30.0, 20.0, 10.0],
        "normal": [0.0, 0.0, 1.0],
        "area_mm2": 2400.0,
        "planar": True,
    }


# ---- describe_edge -----------------------------------------------------------


def test_describe_edge_line_and_full_circle() -> None:
    """Lines get endpoints + length; a full-circle rim gets centre + radius only."""
    adapter = _Harness(None)
    line = fs.describe_edge(adapter, _line((0, 0, 10), (60, 0, 10)))
    assert line["curve"] == "linear"
    assert line["length_mm"] == pytest.approx(60.0)
    rim = fs.describe_edge(adapter, _rim(10))
    assert rim["curve"] == "circular"
    assert rim["radius_mm"] == pytest.approx(4.0)
    assert rim["center_mm"] == pytest.approx([30.0, 20.0, 10.0])
    assert "start_mm" not in rim and "length_mm" not in rim


# ---- select_face_edges through the mixin -----------------------------------


@pytest.mark.asyncio
async def test_side_top_circular_selects_only_the_rim() -> None:
    """side='front' (+Z, the extrude top) + circular -> just the top hole rim."""
    faces, groups = _block()
    harness = _Harness(_model(faces))
    result = await harness.select_face_edges(side="front", edge_type="circular")
    assert result.is_success, result.error
    assert result.data["face"]["normal"] == [0.0, 0.0, 1.0]
    assert [e["curve"] for e in result.data["edges"]] == ["circular"]
    assert result.data["edges"][0]["radius_mm"] == pytest.approx(4.0)
    assert _count_selected(groups["top"]) == 1


@pytest.mark.asyncio
async def test_point_mode_all_edges_clears_then_selects_with_select_data() -> None:
    """A point on the +Z face selects its 5 edges, each via Select4(True, data)."""
    faces, groups = _block()
    model = _model(faces)
    model.SelectionManager.count = 3  # pre-existing selection gets cleared
    harness = _Harness(model)
    result = await harness.select_face_edges(point=[10, 10, 10])
    assert result.is_success, result.error
    assert result.data["selected_edges"] == 5
    for edge in groups["top"]:
        assert edge.selected_with == [(True, "select-data")]
    assert model.SelectionManager.count == 0  # ClearSelection2 ran


@pytest.mark.asyncio
async def test_append_keeps_existing_selection() -> None:
    """append=True does not clear the selection first."""
    faces, _groups = _block()
    model = _model(faces)
    model.SelectionManager.count = 3
    result = await _Harness(model).select_face_edges(side="+Z", append=True)
    assert result.is_success
    assert model.SelectionManager.count == 3


@pytest.mark.asyncio
async def test_plane_mode_uses_reference_plane_geometry() -> None:
    """plane='Front Plane' (z=0) resolves the -Z face lying on it."""
    faces, _groups = _block()
    result = await _Harness(_model(faces)).select_face_edges(plane="Front Plane")
    assert result.is_success, result.error
    assert result.data["face"]["center_mm"] == [30.0, 20.0, 0.0]
    assert len(result.data["faces"]) == 1


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"point": [1000, 1000, 1000]}, "No face found at point"),
        ({"plane": "Nope Plane"}, "No reference plane named 'Nope Plane'"),
        ({"plane": "Mid Plane"}, "No body face lies on 'Mid Plane'"),
        ({"side": "left", "edge_type": "circular"}, "has no circular edges"),
        ({"side": "up"}, "Unknown side"),
    ],
)
@pytest.mark.asyncio
async def test_select_face_edges_errors(kwargs: dict, fragment: str) -> None:
    """Each failure is a clean ERROR (no 'Error in ...' prefix)."""
    faces, _groups = _block()
    result = await _Harness(_model(faces)).select_face_edges(**kwargs)
    assert result.is_error
    assert fragment in (result.error or "")
    assert not (result.error or "").startswith("Error in")


@pytest.mark.asyncio
async def test_select_failure_is_reported() -> None:
    """An edge that refuses Select4 makes the whole call an ERROR."""
    faces, _groups = _block()
    faces[2]._edges = [_line((0, 0, 0), (0, 40, 0), ok=False)]
    model = _model(faces)
    model.SelectionManager.count = 2  # earlier picks that a retry would reuse
    result = await _Harness(model).select_face_edges(side="-X", append=True)
    assert result.is_error
    assert "could not be selected" in (result.error or "")
    assert "selection was cleared" in (result.error or "")
    assert model.SelectionManager.count == 0  # review #3: no partial set left


@pytest.mark.asyncio
async def test_requires_part_and_active_model() -> None:
    """Non-part documents and no model are refused before any COM work."""
    faces, _groups = _block()
    drawing = await _Harness(_model(faces, doc_type=3)).select_face_edges(side="top")
    assert drawing.is_error and "part document" in (drawing.error or "")
    none = await _Harness(None).select_face_edges(side="top")
    assert none.is_error and none.error == "No active model"


class _BrokenFace(_Face):
    """A face whose closest-point query fails, as some COM faces do."""

    def GetClosestPointOn(self, x: float, y: float, z: float) -> list[float]:  # noqa: N802
        raise RuntimeError("closest point unavailable")


@pytest.mark.asyncio
async def test_point_mode_skips_faces_that_cannot_report_a_closest_point() -> None:
    faces, _groups = _block()
    faces.insert(0, _BrokenFace((0, 0, 1), (0, 0, 10, 60, 40, 10), 1, []))

    result = await _Harness(_model(faces)).select_face_edges(point=[30, 20, 10])

    assert result.is_success, result.error
    assert result.data["face"]["center_mm"] == [30.0, 20.0, 10.0]


def _model_with_feature(faces: list[_Face], feature: Any) -> SimpleNamespace:
    model = _model(faces)
    model.FeatureByName = lambda _name: feature
    return model


@pytest.mark.parametrize(
    ("feature", "fragment"),
    [
        (
            SimpleNamespace(GetSpecificFeature2=lambda: None),
            "'Odd' is not a reference plane",
        ),
        (
            SimpleNamespace(
                GetSpecificFeature2=lambda: SimpleNamespace(
                    Transform=SimpleNamespace(ArrayData=[1, 0, 0])
                )
            ),
            "Could not read the geometry of plane 'Odd'",
        ),
    ],
)
@pytest.mark.asyncio
async def test_plane_mode_rejects_non_planes_and_unreadable_geometry(
    feature: Any, fragment: str
) -> None:
    faces, _groups = _block()

    result = await _Harness(_model_with_feature(faces, feature)).select_face_edges(
        plane="Odd"
    )

    assert result.is_error
    assert fragment in (result.error or "")


@pytest.mark.asyncio
async def test_a_part_without_faces_is_an_error() -> None:
    result = await _Harness(_model([])).select_face_edges(side="top")

    assert result.is_error
    assert "no solid body faces" in (result.error or "")


@pytest.mark.asyncio
async def test_side_without_a_planar_face_is_an_error() -> None:
    faces, _groups = _block()
    cylinder_only = [f for f in faces if f.Normal == [0, 0, 0]]

    result = await _Harness(_model(cylinder_only)).select_face_edges(side="top")

    assert result.is_error
    assert "No planar face faces 'top'" in (result.error or "")
