"""Resolve a face by point / side / plane and multi-select its edges (#106).

Split into three single-purpose pieces so each can be tested on its own:

* **Pure geometry** (no COM): side-token parsing, picking the furthest
  planar face facing a direction, matching faces to a reference plane, and
  input validation shared by the real and mock adapters.
* **Edge description** (:func:`describe_edge`): one place that turns an
  ``IEdge`` into a JSON-friendly dict - also used by ``get_selected_entities``.
* **COM access** (:class:`FaceEdgeSelector`): reads faces/edges off the
  active part and performs the multi-selection.

Live behaviour this relies on (R2026x, 2026-10-13) is recorded in
``openspec/changes/wire-unwired-adapter-tools/design.md``: every dispatch must
be method-flagged, ``IFace2.Normal`` is ``[0,0,0]`` for non-planar faces,
``IFace2.GetClosestPointOn`` returns the closest point in its first three
values, a full-circle edge has no vertices, ``IRefPlane.Transform.ArrayData``
holds the plane normal at ``[6:9]`` and origin at ``[9:12]``, and
``IEntity.Select4`` needs a real ``SelectData`` (``None`` is a type mismatch).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .com_utils import as_list, selection_count
from .com_utils import attempt as _attempt
from .com_utils import flag as _flag

#: Outward direction for each accepted ``side`` token (case-insensitive).
#: Aliases follow SolidWorks' default orientation: Front = XY (+Z),
#: Top = XZ (+Y), Right = YZ (+X).
SIDE_VECTORS: dict[str, tuple[float, float, float]] = {
    "+x": (1.0, 0.0, 0.0),
    "-x": (-1.0, 0.0, 0.0),
    "+y": (0.0, 1.0, 0.0),
    "-y": (0.0, -1.0, 0.0),
    "+z": (0.0, 0.0, 1.0),
    "-z": (0.0, 0.0, -1.0),
    "right": (1.0, 0.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "top": (0.0, 1.0, 0.0),
    "bottom": (0.0, -1.0, 0.0),
    "front": (0.0, 0.0, 1.0),
    "back": (0.0, 0.0, -1.0),
}
EDGE_TYPES = ("all", "linear", "circular")

_PARALLEL = 0.999  # |cos| threshold for "same direction"
_ON_PLANE_M = 1e-6  # metres
_ON_FACE_M = 1e-5  # metres (0.01 mm) for point-on-face


# ---- pure helpers ---------------------------------------------------------


def _dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def side_vector(side: str) -> tuple[float, float, float]:
    """Return the unit vector for a side token.

    Raises:
        ValueError: When the token is not one of :data:`SIDE_VECTORS`.
    """
    try:
        return SIDE_VECTORS[side.strip().lower()]
    except KeyError:
        raise ValueError(
            f"Unknown side {side!r}; use one of: " + ", ".join(SIDE_VECTORS)
        ) from None


def validate_face_query(
    point: list[float] | None,
    side: str | None,
    plane: str | None,
    edge_type: str,
) -> str | None:
    """Check a select_face_edges request; return an error message or None."""
    given = [
        name
        for name, value in (("point", point), ("side", side), ("plane", plane))
        if value not in (None, "")
    ]
    if len(given) != 1:
        return (
            "Give exactly one of point, side or plane to identify the face "
            f"(got {', '.join(given) or 'none'})."
        )
    if point is not None and len(point) != 3:
        return "point must be [x, y, z] in millimetres."
    if side is not None:
        try:
            side_vector(side)
        except ValueError as e:
            return str(e)
    if edge_type not in EDGE_TYPES:
        return f"edge_type must be one of {', '.join(EDGE_TYPES)} (got {edge_type!r})."
    return None


@dataclass(frozen=True)
class FaceInfo:
    """Geometry of one body face, in metres.

    Attributes:
        index: Position in the body's face list (stable within one call).
        normal: Outward unit normal; ``(0, 0, 0)`` for non-planar faces.
        box: ``(xmin, ymin, zmin, xmax, ymax, zmax)``.
        area: Face area in m^2.
        handle: The ``IFace2`` dispatch (``None`` in pure tests).
    """

    index: int
    normal: tuple[float, float, float]
    box: tuple[float, float, float, float, float, float]
    area: float
    handle: Any = None

    @property
    def is_planar(self) -> bool:
        """True when SolidWorks reported a non-zero normal."""
        return any(abs(c) > 1e-9 for c in self.normal)

    @property
    def center(self) -> tuple[float, float, float]:
        """Bounding-box centre (lies in the face's plane for planar faces)."""
        b = self.box
        return ((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2)

    def describe(self) -> dict[str, Any]:
        """JSON-friendly summary in millimetres."""
        return {
            "index": self.index,
            "center_mm": [round(c * 1000, 6) for c in self.center],
            "normal": [round(c, 6) + 0.0 for c in self.normal],
            "area_mm2": round(self.area * 1e6, 6),
            "planar": self.is_planar,
        }


def pick_side_face(
    faces: list[FaceInfo], direction: tuple[float, float, float]
) -> FaceInfo | None:
    """Return the planar face facing ``direction`` that lies furthest along it.

    Ties (same offset within 0.1 µm) go to the larger face.
    """
    facing = [
        f for f in faces if f.is_planar and _dot(f.normal, direction) >= _PARALLEL
    ]
    if not facing:
        return None
    return max(facing, key=lambda f: (round(_dot(f.center, direction), 7), f.area))


def plane_from_transform(
    array_data: list[float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return ``(origin, normal)`` from ``IRefPlane.Transform.ArrayData``."""
    normal = (float(array_data[6]), float(array_data[7]), float(array_data[8]))
    origin = (float(array_data[9]), float(array_data[10]), float(array_data[11]))
    return origin, normal


def faces_on_plane(
    faces: list[FaceInfo],
    origin: tuple[float, float, float],
    normal: tuple[float, float, float],
) -> list[FaceInfo]:
    """Return the planar faces that lie in the given plane."""
    out = []
    for f in faces:
        if not f.is_planar or abs(_dot(f.normal, normal)) < _PARALLEL:
            continue
        offset = tuple(c - o for c, o in zip(f.center, origin, strict=True))
        if abs(_dot(offset, normal)) <= _ON_PLANE_M:
            out.append(f)
    return out


def edge_matches(kind: str, edge_type: str) -> bool:
    """Whether an edge of ``kind`` passes the ``edge_type`` filter."""
    return edge_type == "all" or kind == edge_type


# ---- COM: edge description -----------------------------------------------


#: Exactly the members read below. Flagging a whole interface costs ~27 ms
#: per fresh dispatch (see ``_WALK_MEMBERS`` in pywin32_adapter); a face can
#: hand back dozens of edges/curves/vertices, so flag just what is used.
_EDGE_MEMBERS = ("GetCurve", "GetStartVertex", "GetEndVertex", "Select4")
_FACE_MEMBERS = ("GetBox", "GetArea", "GetEdges", "GetClosestPointOn")


def describe_edge(adapter: Any, edge: Any) -> dict[str, Any]:
    """Describe an ``IEdge`` in millimetres; unresolvable fields are omitted.

    Returns:
        dict[str, Any]: ``curve`` (``linear``/``circular``/``other``), plus
        ``start_mm``/``end_mm``/``length_mm`` when the edge has vertices
        (straight-line length - a curved edge is longer), and
        ``center_mm``/``axis``/``radius_mm`` for circular edges.
    """
    _flag(adapter, edge, *_EDGE_MEMBERS)
    entry: dict[str, Any] = {"curve": "other"}

    curve = _attempt(adapter, lambda: edge.GetCurve())
    if curve is not None:
        _flag(adapter, curve, "IsCircle", "IsLine")
        if _attempt(adapter, lambda: curve.IsCircle(), False):
            entry["curve"] = "circular"
            params = _attempt(adapter, lambda: list(curve.CircleParams))
            if params and len(params) >= 7:
                entry["center_mm"] = [c * 1000 for c in params[0:3]]
                entry["axis"] = [round(float(c), 6) + 0.0 for c in params[3:6]]
                entry["radius_mm"] = params[6] * 1000
        elif _attempt(adapter, lambda: curve.IsLine(), False):
            entry["curve"] = "linear"

    points = []
    for getter in ("GetStartVertex", "GetEndVertex"):
        vertex = _attempt(adapter, lambda g=getter: getattr(edge, g)())
        if vertex is None:
            points.append(None)
            continue
        _flag(adapter, vertex, "GetPoint")
        points.append(_attempt(adapter, lambda v=vertex: v.GetPoint()))
    start, end = points
    if start:
        entry["start_mm"] = [c * 1000 for c in start]
    if end:
        entry["end_mm"] = [c * 1000 for c in end]
    if start and end:
        entry["length_mm"] = (
            sum((a - b) ** 2 for a, b in zip(start, end, strict=True)) ** 0.5 * 1000
        )
    return entry


# ---- COM: face resolution + selection -----------------------------------


class FaceEdgeSelector:
    """Resolve a face on the active part and multi-select its edges.

    Args:
        adapter: A connected ``PyWin32Adapter`` (needs ``currentModel`` and
            ``_attempt``).
    """

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    @property
    def _model(self) -> Any:
        return self._adapter.currentModel

    def faces(self) -> list[FaceInfo]:
        """Return every face of every solid body on the active part."""
        part = self._model
        _flag(self._adapter, part, "GetBodies2")
        bodies = as_list(_attempt(self._adapter, lambda: part.GetBodies2(0, False)))
        out: list[FaceInfo] = []
        for body in bodies:
            _flag(self._adapter, body, "GetFaces")
            for face in _attempt(self._adapter, lambda b=body: b.GetFaces()) or []:
                _flag(self._adapter, face, *_FACE_MEMBERS)
                normal = _attempt(self._adapter, lambda f=face: list(f.Normal)) or [
                    0,
                    0,
                    0,
                ]
                box = (
                    _attempt(self._adapter, lambda f=face: list(f.GetBox())) or [0] * 6
                )
                area = _attempt(self._adapter, lambda f=face: f.GetArea()) or 0.0
                out.append(
                    FaceInfo(
                        index=len(out),
                        normal=tuple(float(c) for c in normal[:3]),  # type: ignore[arg-type]
                        box=tuple(float(c) for c in box[:6]),  # type: ignore[arg-type]
                        area=float(area),
                        handle=face,
                    )
                )
        return out

    def face_at_point(self, faces: list[FaceInfo], point_mm: list[float]) -> FaceInfo:
        """Return the face containing ``point_mm`` (closest within 0.01 mm)."""
        q = tuple(c / 1000.0 for c in point_mm)
        best: tuple[float, FaceInfo] | None = None
        for f in faces:
            closest = _attempt(
                self._adapter, lambda f=f: list(f.handle.GetClosestPointOn(*q))
            )
            if not closest or len(closest) < 3:
                continue
            d = sum((a - b) ** 2 for a, b in zip(closest[:3], q, strict=True)) ** 0.5
            if best is None or d < best[0]:
                best = (d, f)
        if best is None or best[0] > _ON_FACE_M:
            raise LookupError(f"No face found at point {list(point_mm)} mm.")
        return best[1]

    def plane_geometry(
        self, plane: str
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Return ``(origin, normal)`` of a named reference plane."""
        feature = _attempt(self._adapter, lambda: self._model.FeatureByName(plane))
        if feature is None:
            raise LookupError(f"No reference plane named {plane!r}.")
        _flag(self._adapter, feature, "GetSpecificFeature2")
        ref = _attempt(self._adapter, lambda: feature.GetSpecificFeature2())
        if ref is None:
            raise LookupError(f"{plane!r} is not a reference plane.")
        data = _attempt(self._adapter, lambda: list(ref.Transform.ArrayData))
        if not data or len(data) < 12:
            raise LookupError(f"Could not read the geometry of plane {plane!r}.")
        return plane_from_transform(data)

    def resolve(
        self, point: list[float] | None, side: str | None, plane: str | None
    ) -> list[FaceInfo]:
        """Resolve the request to one face (or several for ``plane``)."""
        faces = self.faces()
        if not faces:
            raise LookupError("The active part has no solid body faces.")
        if point is not None:
            return [self.face_at_point(faces, point)]
        if side is not None:
            face = pick_side_face(faces, side_vector(side))
            if face is None:
                raise LookupError(f"No planar face faces {side!r}.")
            return [face]
        origin, normal = self.plane_geometry(str(plane))
        on_plane = faces_on_plane(faces, origin, normal)
        if not on_plane:
            raise LookupError(f"No body face lies on {plane!r}.")
        return on_plane

    def edges(
        self, faces: list[FaceInfo], edge_type: str
    ) -> list[tuple[Any, dict[str, Any]]]:
        """Return ``(edge, description)`` for the faces' edges passing the filter."""
        out = []
        for f in faces:
            for edge in _attempt(self._adapter, lambda f=f: f.handle.GetEdges()) or []:
                info = describe_edge(self._adapter, edge)
                if edge_matches(info["curve"], edge_type):
                    info["face_index"] = f.index
                    out.append((edge, info))
        return out

    def select(
        self, edges: list[tuple[Any, dict[str, Any]]], append: bool
    ) -> int | None:
        """Select every edge; return the selection count afterwards.

        All or nothing: if any edge refuses to select, the selection is
        cleared before raising, so a following ``add_chamfer`` /
        ``add_fillet`` with empty ``edge_names`` cannot silently act on a
        partial set.

        Raises:
            RuntimeError: When any edge refuses to select.
        """
        model = self._model
        sel_mgr = model.SelectionManager
        _flag(self._adapter, sel_mgr, "CreateSelectData")
        if not append:
            _attempt(self._adapter, lambda: model.ClearSelection2(True))
        select_data = _attempt(self._adapter, lambda: sel_mgr.CreateSelectData())
        failed = []
        for i, (edge, _info) in enumerate(edges):
            _flag(self._adapter, edge, "Select4")
            if not _attempt(
                self._adapter, lambda e=edge: e.Select4(True, select_data), False
            ):
                failed.append(i)
        if failed:
            _attempt(self._adapter, lambda: model.ClearSelection2(True))
            raise RuntimeError(
                f"{len(failed)} of {len(edges)} edge(s) could not be selected "
                f"(indices {failed}); the selection was cleared so nothing acts "
                "on a partial set."
            )
        return selection_count(self._adapter, model)
