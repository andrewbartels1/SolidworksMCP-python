"""Tests for the overlap-free dimension layout and the A3 standard layout maths."""

from __future__ import annotations

from solidworks_mcp.adapters.solidworks import dimension_layout as lay
from solidworks_mcp.adapters.solidworks import drawing_standard as std


def _hdim(
    key: str, view: str, x0: float, x1: float, y_line: float, edge: float
) -> lay.DimensionGeometry:
    """A horizontal dimension spanning x0..x1 with its line at y_line."""
    cx = (x0 + x1) / 2
    return lay.DimensionGeometry(
        key=key,
        view=view,
        text_box=(cx - 0.005, y_line - 0.0016, cx + 0.005, y_line + 0.0016),
        position=(cx, y_line),
        lines=[
            (x0, edge, x0, y_line),
            (x1, edge, x1, y_line),
            (x0, y_line, x1, y_line),
        ],
    )


def _vdim(
    key: str, view: str, y0: float, y1: float, x_line: float, edge: float
) -> lay.DimensionGeometry:
    cy = (y0 + y1) / 2
    return lay.DimensionGeometry(
        key=key,
        view=view,
        text_box=(x_line - 0.004, cy - 0.0016, x_line + 0.004, cy + 0.0016),
        position=(x_line, cy),
        lines=[
            (edge, y0, x_line, y0),
            (edge, y1, x_line, y1),
            (x_line, y0, x_line, y1),
        ],
    )


def _apply(
    dims: list[lay.DimensionGeometry], moves: dict
) -> list[lay.DimensionGeometry]:
    """Apply planned moves the way SetPosition would (text and lines shift)."""
    out = []
    for d in dims:
        dx, dy = moves.get(d.key, (0.0, 0.0))
        orient, _span, ends = lay.classify(d.lines)
        box = lay.shift_box(d.text_box, dx, dy)
        out.append(
            lay.DimensionGeometry(
                key=d.key,
                view=d.view,
                text_box=box,
                position=(d.position[0] + dx, d.position[1] + dy),
                lines=lay._projected_segments(d, dx, dy, OUTLINE),
            )
        )
    return out


OUTLINE = (0.050, 0.100, 0.170, 0.170)  # a 120 x 70 mm view


class TestGeometry:
    def test_box_overlap_and_inside(self) -> None:
        assert lay.box_overlap((0, 0, 1, 1), (0.5, 0.5, 2, 2))
        assert not lay.box_overlap((0, 0, 1, 1), (1.1, 0, 2, 1))
        assert lay.inside((0.2, 0.2, 0.8, 0.8), (0, 0, 1, 1))
        assert not lay.inside((0.2, 0.2, 1.2, 0.8), (0, 0, 1, 1))

    def test_segment_hits_box(self) -> None:
        assert lay.segment_hits_box((-1, 0.5, 2, 0.5), (0, 0, 1, 1))
        assert not lay.segment_hits_box((-1, 2, 2, 2), (0, 0, 1, 1))

    def test_classify(self) -> None:
        h = _hdim("h", "v", 0.05, 0.17, 0.09, 0.1)
        v = _vdim("v", "v", 0.1, 0.17, 0.04, 0.05)
        assert lay.classify(h.lines)[0] == "h"
        assert abs(lay.classify(h.lines)[1] - 0.12) < 1e-9
        assert lay.classify(v.lines)[0] == "v"


class TestLayout:
    def test_dimensions_inside_the_view_are_reported(self) -> None:
        inside_dim = _hdim("a", "View1", 0.05, 0.17, 0.12, 0.1)  # text on the part
        problems = lay.find_overlaps([inside_dim], {"View1": OUTLINE})
        assert {p["kind"] for p in problems} == {"on_view_geometry"}

    def test_plan_moves_everything_clear_with_standard_spacing(self) -> None:
        dims = [
            _hdim("w", "View1", 0.05, 0.17, 0.12, 0.10),  # 120 wide, inside the view
            _hdim("hole", "View1", 0.05, 0.09, 0.13, 0.10),  # shorter, also inside
            _vdim("h", "View1", 0.10, 0.17, 0.11, 0.05),  # 70 high, inside
        ]
        moves, unplaced = lay.plan_layout(
            dims, {"View1": OUTLINE}, (0.015, 0.015, 0.405, 0.282)
        )
        assert not unplaced
        moved = _apply(dims, moves)
        assert lay.find_overlaps(moved, {"View1": OUTLINE}) == []
        by_key = {d.key: d for d in moved}
        # Shortest span sits nearest the view: first row 8 mm out, next 7 mm further.
        rows = sorted(
            abs((by_key[k].text_box[1] + by_key[k].text_box[3]) / 2 - OUTLINE[1])
            for k in ("w", "hole")
        )
        assert abs(rows[0] - lay.FIRST_OFFSET) < 1e-6
        assert abs(rows[1] - rows[0] - lay.ROW_PITCH) < 1e-6

    def test_obstacles_are_avoided(self) -> None:
        dims = [_hdim("w", "View1", 0.05, 0.17, 0.12, 0.10)]
        below = (0.0, 0.0, 0.3, 0.1)  # everything below the view is blocked
        moves, _ = lay.plan_layout(dims, {"View1": OUTLINE}, None, {"caption": below})
        moved = _apply(dims, moves)
        assert moved[0].text_box[1] > OUTLINE[3]  # went above instead
        assert (
            lay.find_overlaps(moved, {"View1": OUTLINE}, None, {"caption": below}) == []
        )

    def test_note_overlaps_are_reported(self) -> None:
        notes = {
            "NOTES": (0.02, 0.06, 0.05, 0.065),
            "line 1": (0.02, 0.062, 0.09, 0.066),
        }
        problems = lay.find_annotation_overlaps(
            notes, [], {}, None, {"title block": std.TITLE_BLOCK}
        )
        assert [p["kind"] for p in problems] == ["note_on_note"]


class TestStandardSheet:
    PLATE = {"front": (0.12, 0.01), "plan": (0.12, 0.07), "side": (0.07, 0.01)}

    def test_plate_fills_the_sheet(self) -> None:
        scale, cells = std.choose_layout(self.PLATE)
        assert scale == (1.5, 1)
        for name in ("front", "side", "plan", "iso"):
            assert lay.inside(cells[name], std.VIEW_ZONE)
            assert not lay.box_overlap(cells[name], std.TITLE_BLOCK)

    def test_large_part_uses_a_smaller_standard_scale(self) -> None:
        scale, _ = std.choose_layout(
            {"front": (0.4, 0.3), "plan": (0.4, 0.25), "side": (0.25, 0.3)}
        )
        assert scale in std.STANDARD_SCALES and scale[0] / scale[1] < 1

    def test_cells_do_not_overlap(self) -> None:
        _, cells = std.choose_layout(self.PLATE)
        names = ["front", "side", "plan", "iso", "notes"]
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                assert not lay.box_overlap(cells[a], cells[b], -1e-9), (a, b)

    def test_iso_fit_and_labels(self) -> None:
        assert std.scale_label((1, 2)) == "1:2"
        assert std.scale_label((2.5, 1)) == "2.5:1"
        _, cells = std.choose_layout(self.PLATE)
        assert std.iso_fit_scale((0.15, 0.09), cells["iso"]) in std.STANDARD_SCALES

    def test_title_block_properties(self) -> None:
        model, drawing = std.title_block_properties(
            model_file=r"C:\parts\Mounting Plate.SLDPRT",
            title="Mounting Plate - Rev A",
            subtitle="Part drawing",
            author="J. Smith",
            drawn_date="17 Oct 2026",
            revision="A",
            company="",
        )
        assert (
            model["Description"] == "Mounting Plate - Rev A"
        )  # short: subtitle not appended
        assert model["Material"] == '"SW-Material@Mounting Plate.SLDPRT"'
        assert model["Weight"] == '"SW-Mass@Mounting Plate.SLDPRT"'
        assert drawing["COMPANYNAME"] == "Part drawing"
        assert drawing["DrawnBy"] == "J. Smith"
