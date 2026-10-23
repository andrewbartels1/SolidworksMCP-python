"""Overlap-free placement of drawing dimensions (pure geometry, no COM).

Rule enforced: **nothing on the sheet may overlap.** A dimension's text box must
not intersect another dimension's text, be crossed by another dimension's lines,
sit on any view's geometry, touch an obstacle (title block, view captions, note
blocks) or leave the working area of the frame. A dimension's lines must not
cross another view, and its extension lines must not run across its own view to
the far side.

``InsertModelAnnotations3`` places imported dimensions where they sit in the
model sketch, which on a drawing view lands them *inside* the view outline, on
top of the part and of each other (measured live on SW 2025).

:func:`plan_layout` moves each dimension outside its view, following the
A3 drafting standard
(``drawing_standard.py``): horizontal dimensions in rows above/below the part, rows 7 mm
apart; vertical dimensions in columns left/right, 9 mm apart; the first row
8 mm from the outline, on the side its extension lines start from. Others
(diameters, radii, angles) go diagonally outward. Rows are filled shortest span first, so the extension lines of longer
outer dimensions clear the inner text. Every candidate position is checked
against everything already placed; the first free one wins.

All coordinates are sheet metres; boxes and segments are ``(x0, y0, x1, y1)``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

Box = tuple[float, float, float, float]
Segment = tuple[float, float, float, float]

#: Clearance kept around every text box when testing overlaps (0.75 mm).
TEXT_PADDING = 0.00075
#: First row of dimensions: 8 mm from the part outline.
FIRST_OFFSET = 0.008
#: Horizontal-dimension rows 7 mm apart.
ROW_PITCH = 0.007
#: Vertical-dimension columns 9 mm apart.
COLUMN_PITCH = 0.009
#: Gap used when a text box is bigger than the standard pitch allows.
STACK_GAP = 0.0035
#: Outward steps tried per side before giving up on that side.
MAX_STEPS = 12
#: Another view's outline is grown by 0.2 mm, so a line along its edge counts.
EDGE_TOLERANCE = 0.0002
#: More than 1 mm of a line on another view is a crossing; touching is not.
MIN_CROSSING = 0.001


def text_box(x: float, y: float, width: float, height: float, angle: float) -> Box:
    """Sheet box of a text run anchored at its lower-left corner and turned.

    ``IDisplayData`` gives each text's lower-left corner, length, height and
    angle. A vertical dimension's text is turned 90 degrees, so it runs up the
    sheet from that corner and lies to its left (measured live on SW 2026).

    Args:
        x: Lower-left corner x.
        y: Lower-left corner y.
        width: Text length along its baseline.
        height: Text height.
        angle: Baseline angle in radians, counter-clockwise.

    Returns:
        Box: The axis-aligned box around the turned text.
    """
    c, s = math.cos(angle), math.sin(angle)
    corners = [(0.0, 0.0), (width, 0.0), (0.0, height), (width, height)]
    xs = [x + u * c - v * s for u, v in corners]
    ys = [y + u * s + v * c for u, v in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def crosses_other_view(
    lines: list[Segment], own_view: str, outlines: dict[str, Box]
) -> str | None:
    """Return the first other view any of ``lines`` runs across or along.

    A dimension's extension lines start on its own view's geometry, so its own
    outline is exempt. On any other view, more than :data:`MIN_CROSSING` of a
    line inside that outline (grown by :data:`EDGE_TOLERANCE`, so a line lying
    along its edge counts) is a crossing; a line ending at the edge is not.
    Measured live on SW 2026: a front view's height dimension parked beyond
    the side view drew its extension lines along the side view's top and
    bottom edges, straight across it.

    Args:
        lines: The dimension's line segments.
        own_view: The view the dimension belongs to.
        outlines: View name -> view outline.

    Returns:
        str | None: The crossed view's name, or ``None`` when clear.
    """
    t = EDGE_TOLERANCE
    for view, o in outlines.items():
        if view == own_view:
            continue
        grown = (o[0] - t, o[1] - t, o[2] + t, o[3] + t)
        if any(length_inside(s, grown) > MIN_CROSSING for s in lines):
            return view
    return None


@dataclass
class DimensionGeometry:
    """One drawing dimension as read from ``IAnnotation::GetDisplayData``.

    Attributes:
        key: Stable identifier (view name + index).
        view: Owning view name.
        text_box: Current text box on the sheet.
        position: ``IAnnotation::GetPosition`` (x, y) - what ``SetPosition`` moves.
        lines: Every line segment of the dimension (extension + dimension lines).
        orientation: ``"h"``, ``"v"`` or ``None``; set by :func:`plan_layout`.
        span: Distance between the extension lines (0 when unknown).
    """

    key: str
    view: str
    text_box: Box
    position: tuple[float, float]
    lines: list[Segment] = field(default_factory=list)
    orientation: str | None = None
    span: float = 0.0


def box_overlap(a: Box, b: Box, pad: float = 0.0) -> bool:
    """Return True when two boxes intersect (after growing each by ``pad``)."""
    return not (
        a[2] + pad <= b[0] - pad
        or b[2] + pad <= a[0] - pad
        or a[3] + pad <= b[1] - pad
        or b[3] + pad <= a[1] - pad
    )


def inside(box: Box, area: Box) -> bool:
    """Return True when ``box`` lies entirely within ``area``."""
    return (
        area[0] <= box[0]
        and box[2] <= area[2]
        and area[1] <= box[1]
        and box[3] <= area[3]
    )


def segment_hits_box(seg: Segment, box: Box) -> bool:
    """Liang-Barsky clip: True when the segment passes through the box."""
    x0, y0, x1, y1 = seg
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in (
        (-dx, x0 - box[0]),
        (dx, box[2] - x0),
        (-dy, y0 - box[1]),
        (dy, box[3] - y0),
    ):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def length_inside(seg: Segment, box: Box) -> float:
    """Length of the part of a segment that lies inside a box (Liang-Barsky).

    Args:
        seg: The segment.
        box: The box.

    Returns:
        float: 0.0 when the segment misses the box.
    """
    x0, y0, x1, y1 = seg
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in (
        (-dx, x0 - box[0]),
        (dx, box[2] - x0),
        (-dy, y0 - box[1]),
        (dy, box[3] - y0),
    ):
        if abs(p) < 1e-12:
            if q < 0:
                return 0.0
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return 0.0
    return (t1 - t0) * (dx * dx + dy * dy) ** 0.5


def shift_box(box: Box, dx: float, dy: float) -> Box:
    """Translate a box."""
    return (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)


def classify(lines: list[Segment]) -> tuple[str | None, float, list[float]]:
    """Work out orientation, span and extension-line coordinates.

    SolidWorks returns a linear dimension's two extension lines first. Both
    vertical means a horizontal dimension (their x values are the span ends);
    both horizontal means a vertical one.

    Returns:
        tuple: orientation, span, and the two extension-line coordinates.
    """
    if len(lines) >= 2:
        a, b = lines[0], lines[1]
        tol = 1e-6
        if abs(a[0] - a[2]) < tol and abs(b[0] - b[2]) < tol and abs(a[0] - b[0]) > tol:
            return "h", abs(a[0] - b[0]), sorted([a[0], b[0]])
        if abs(a[1] - a[3]) < tol and abs(b[1] - b[3]) < tol and abs(a[1] - b[1]) > tol:
            return "v", abs(a[1] - b[1]), sorted([a[1], b[1]])
    return None, 0.0, []


def extension_origins(dim: DimensionGeometry) -> list[float]:
    """Where each extension line starts on the part, across the dimension.

    An extension line runs from the part to just past the dimension line, so
    its start is the end farther from the text: a y for a horizontal
    dimension, an x for a vertical one.

    Args:
        dim: The dimension.

    Returns:
        list[float]: One coordinate per extension line; empty for a leader.
    """
    orient = classify(dim.lines)[0]
    if orient is None:
        return []
    axis = 1 if orient == "h" else 0
    centre = (dim.text_box[axis] + dim.text_box[axis + 2]) / 2.0
    return [
        max((s[axis], s[axis + 2]), key=lambda c: abs(c - centre))
        for s in dim.lines[:2]
    ]


def crosses_own_view(dim: DimensionGeometry, outline: Box) -> bool:
    """True when an extension line runs across its own view to the far side.

    Measured live on SW 2026: a height dimension moved from the left of the
    top view to its right drew both extension lines straight across the view.

    Args:
        dim: The dimension.
        outline: Its view's outline.

    Returns:
        bool: ``False`` for leaders, which have no extension lines.
    """
    axis = 1 if classify(dim.lines)[0] == "h" else 0
    low, high = outline[axis], outline[axis + 2]
    middle = (low + high) / 2.0
    for start, line in zip(extension_origins(dim), dim.lines, strict=False):
        end = line[axis + 2] if line[axis] == start else line[axis]
        if (start < middle and end > high) or (start > middle and end < low):
            return True
    return False


def _projected_segments(
    dim: DimensionGeometry, dx: float, dy: float, outline: Box
) -> list[Segment]:
    """Approximate a moved dimension's new dimension and extension lines.

    The extension lines still start where they did on the part and now reach
    the moved dimension line.
    """
    orient, _span, ends = classify(dim.lines)
    box = shift_box(dim.text_box, dx, dy)
    origins = extension_origins(dim)
    if orient == "h":
        y = (box[1] + box[3]) / 2.0
        return [(ends[0], y, ends[1], y)] + [
            (s[0], o, s[0], y) for s, o in zip(dim.lines, origins, strict=False)
        ]
    if orient == "v":
        x = (box[0] + box[2]) / 2.0
        return [(x, ends[0], x, ends[1])] + [
            (o, s[1], x, s[1]) for s, o in zip(dim.lines, origins, strict=False)
        ]
    return [(s[0] + dx, s[1] + dy, s[2] + dx, s[3] + dy) for s in dim.lines]


def find_overlaps(
    dims: list[DimensionGeometry],
    outlines: dict[str, Box],
    sheet: Box | None = None,
    obstacles: dict[str, Box] | None = None,
) -> list[dict[str, str]]:
    """List every rule violation among dimensions as they currently sit.

    Args:
        dims: Dimensions with their real (read-back) geometry.
        outlines: View name -> view outline box.
        sheet: Working area of the frame, when known.
        obstacles: Named boxes nothing may touch (title block, captions, notes).

    Returns:
        list[dict[str, str]]: ``{"dimension", "conflicts_with", "kind"}`` entries.
    """
    problems: list[dict[str, str]] = []
    for i, dim in enumerate(dims):
        for view, outline in outlines.items():
            if box_overlap(dim.text_box, outline, -TEXT_PADDING / 2):
                problems.append(
                    {
                        "dimension": dim.key,
                        "conflicts_with": view,
                        "kind": "on_view_geometry",
                    }
                )
        crossed = crosses_other_view(dim.lines, dim.view, outlines)
        if crossed is not None:
            problems.append(
                {
                    "dimension": dim.key,
                    "conflicts_with": crossed,
                    "kind": "line_through_view",
                }
            )
        own = outlines.get(dim.view)
        if own is not None and crosses_own_view(dim, own):
            problems.append(
                {
                    "dimension": dim.key,
                    "conflicts_with": dim.view,
                    "kind": "line_through_own_view",
                }
            )
        for label, obstacle in (obstacles or {}).items():
            if box_overlap(dim.text_box, obstacle, TEXT_PADDING / 2) or any(
                segment_hits_box(s, obstacle) for s in dim.lines
            ):
                problems.append(
                    {
                        "dimension": dim.key,
                        "conflicts_with": label,
                        "kind": "on_obstacle",
                    }
                )
        if sheet is not None and not inside(dim.text_box, sheet):
            problems.append(
                {
                    "dimension": dim.key,
                    "conflicts_with": "frame",
                    "kind": "outside_working_area",
                }
            )
        for j, other in enumerate(dims):
            if j == i:
                continue
            if j > i and box_overlap(dim.text_box, other.text_box, TEXT_PADDING):
                problems.append(
                    {
                        "dimension": dim.key,
                        "conflicts_with": other.key,
                        "kind": "text_on_text",
                    }
                )
            if any(segment_hits_box(s, dim.text_box) for s in other.lines):
                problems.append(
                    {
                        "dimension": dim.key,
                        "conflicts_with": other.key,
                        "kind": "line_through_text",
                    }
                )
    return problems


def _candidates(
    dim: DimensionGeometry, outline: Box, stack_depth: dict[tuple[str, str], float]
) -> list[tuple[str, float, float]]:
    """Ordered (side, dx, dy) moves to try for one dimension.

    A linear dimension only goes to the side its extension lines start from;
    on the far side they would cross its own view.
    """
    tb = dim.text_box
    w, h = tb[2] - tb[0], tb[3] - tb[1]
    cx, cy = (tb[0] + tb[2]) / 2.0, (tb[1] + tb[3]) / 2.0
    ox, oy = (outline[0] + outline[2]) / 2.0, (outline[1] + outline[3]) / 2.0
    origins = extension_origins(dim)
    out: list[tuple[str, float, float]] = []
    if dim.orientation == "h":
        sides = list(dict.fromkeys("above" if o >= oy else "below" for o in origins))
        pitch = max(ROW_PITCH, h + STACK_GAP)
        for side in sides:
            base = stack_depth.get((dim.view, side), 0.0)
            for step in range(MAX_STEPS):
                off = FIRST_OFFSET + base + step * pitch
                target = outline[3] + off if side == "above" else outline[1] - off
                out.append((side, 0.0, target - cy))
    elif dim.orientation == "v":
        sides = list(dict.fromkeys("right" if o >= ox else "left" for o in origins))
        pitch = max(COLUMN_PITCH, w + STACK_GAP)
        for side in sides:
            base = stack_depth.get((dim.view, side), 0.0)
            for step in range(MAX_STEPS):
                off = FIRST_OFFSET + base + step * pitch
                target = outline[2] + off if side == "right" else outline[0] - off
                out.append((side, target - cx, 0.0))
    else:
        corners = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
        corners.sort(key=lambda c: -((cx - ox) * c[0] + (cy - oy) * c[1]))
        for sx, sy in corners:
            for step in range(MAX_STEPS):
                off = FIRST_OFFSET + step * ROW_PITCH
                tx = (
                    (outline[2] + off + w / 2.0)
                    if sx > 0
                    else (outline[0] - off - w / 2.0)
                )
                ty = (
                    (outline[3] + off + h / 2.0)
                    if sy > 0
                    else (outline[1] - off - h / 2.0)
                )
                out.append((f"corner{sx}{sy}", tx - cx, ty - cy))
    return out


def plan_layout(
    dims: list[DimensionGeometry],
    outlines: dict[str, Box],
    sheet: Box | None = None,
    obstacles: dict[str, Box] | None = None,
) -> tuple[dict[str, tuple[float, float]], list[str]]:
    """Choose a move for every dimension so the overlap rule holds.

    Args:
        dims: Dimensions with their current geometry.
        outlines: View name -> view outline.
        sheet: Working area of the frame, when known.
        obstacles: Named boxes nothing may touch.

    Returns:
        tuple: ``{key: (dx, dy)}`` moves, and keys that found no free spot
        (left in place and reported by the caller's final check).
    """
    blocked = list((obstacles or {}).values())
    for dim in dims:
        dim.orientation, dim.span, _ = classify(dim.lines)
    order = sorted(dims, key=lambda d: (d.view, d.orientation or "z", d.span))
    placed_boxes: list[Box] = []
    placed_lines: list[Segment] = []
    stack_depth: dict[tuple[str, str], float] = {}
    moves: dict[str, tuple[float, float]] = {}
    unplaced: list[str] = []
    for dim in order:
        outline = outlines.get(dim.view)
        if outline is None:
            unplaced.append(dim.key)
            continue
        chosen = None
        for side, dx, dy in _candidates(dim, outline, stack_depth):
            box = shift_box(dim.text_box, dx, dy)
            if any(box_overlap(box, o, TEXT_PADDING) for o in outlines.values()):
                continue
            if any(box_overlap(box, o, TEXT_PADDING) for o in blocked):
                continue
            if sheet is not None and not inside(box, sheet):
                continue
            if any(box_overlap(box, p, TEXT_PADDING) for p in placed_boxes):
                continue
            if any(segment_hits_box(s, box) for s in placed_lines):
                continue
            segs = _projected_segments(dim, dx, dy, outline)
            if crosses_other_view(segs, dim.view, outlines) is not None:
                continue
            if any(
                segment_hits_box(s, p) for s in segs for p in placed_boxes + blocked
            ):
                continue
            chosen = (side, dx, dy, box, segs)
            break
        if chosen is None:
            unplaced.append(dim.key)
            placed_boxes.append(dim.text_box)
            placed_lines.extend(dim.lines)
            continue
        side, dx, dy, box, segs = chosen
        moves[dim.key] = (dx, dy)
        placed_boxes.append(box)
        placed_lines.extend(segs)
        cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
        if side in {"above", "below"}:
            used = (cy - outline[3]) if side == "above" else (outline[1] - cy)
            pitch = max(ROW_PITCH, box[3] - box[1] + STACK_GAP)
        elif side in {"left", "right"}:
            used = (cx - outline[2]) if side == "right" else (outline[0] - cx)
            pitch = max(COLUMN_PITCH, box[2] - box[0] + STACK_GAP)
        else:
            continue
        stack_depth[(dim.view, side)] = max(
            stack_depth.get((dim.view, side), 0.0), used - FIRST_OFFSET + pitch
        )
    return moves, unplaced


def find_annotation_overlaps(
    notes: dict[str, Box],
    dims: list[DimensionGeometry],
    outlines: dict[str, Box],
    sheet: Box | None = None,
    obstacles: dict[str, Box] | None = None,
) -> list[dict[str, str]]:
    """Check sheet notes and captions against everything else on the sheet.

    Args:
        notes: Label -> measured text box of each note or caption.
        dims: Dimensions with their real geometry.
        outlines: View outlines.
        sheet: Working area of the frame.
        obstacles: Named boxes notes may not touch (title block).

    Returns:
        list[dict[str, str]]: ``{"dimension", "conflicts_with", "kind"}`` entries
        (``dimension`` holds the note label, for one report format).
    """
    problems: list[dict[str, str]] = []
    labels = list(notes)
    for i, label in enumerate(labels):
        box = notes[label]
        for other in labels[i + 1 :]:
            if box_overlap(box, notes[other], TEXT_PADDING / 2):
                problems.append(
                    {
                        "dimension": label,
                        "conflicts_with": other,
                        "kind": "note_on_note",
                    }
                )
        for view, outline in outlines.items():
            if box_overlap(box, outline, 0.0):
                problems.append(
                    {"dimension": label, "conflicts_with": view, "kind": "note_on_view"}
                )
        for name, obstacle in (obstacles or {}).items():
            if box_overlap(box, obstacle, 0.0):
                problems.append(
                    {
                        "dimension": label,
                        "conflicts_with": name,
                        "kind": "note_on_obstacle",
                    }
                )
        if sheet is not None and not inside(box, sheet):
            problems.append(
                {
                    "dimension": label,
                    "conflicts_with": "frame",
                    "kind": "note_outside_working_area",
                }
            )
        for dim in dims:
            if box_overlap(box, dim.text_box, TEXT_PADDING / 2) or any(
                segment_hits_box(s, box) for s in dim.lines
            ):
                problems.append(
                    {
                        "dimension": label,
                        "conflicts_with": dim.key,
                        "kind": "note_on_dimension",
                    }
                )
    return problems
