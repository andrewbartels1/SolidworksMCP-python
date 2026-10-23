"""Tests for the overlap-free dimension layout and the A3 standard layout maths."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.solidworks import dimension_layout as lay


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


def _radial(key: str, view: str, cx: float, cy: float) -> lay.DimensionGeometry:
    """A diameter-style dimension: one diagonal leader, no extension lines."""
    return lay.DimensionGeometry(
        key=key,
        view=view,
        text_box=(cx - 0.004, cy - 0.0016, cx + 0.004, cy + 0.0016),
        position=(cx, cy),
        lines=[(cx - 0.01, cy - 0.01, cx, cy)],
    )


def _kinds(problems: list[dict[str, str]]) -> set[str]:
    return {p["kind"] for p in problems}


class TestGeometryEdges:
    def test_a_leader_has_no_orientation(self) -> None:
        assert lay.classify([(0.0, 0.0, 0.01, 0.01)]) == (None, 0.0, [])

    def test_a_parallel_segment_beside_the_box_misses_it(self) -> None:
        assert not lay.segment_hits_box((-1, 2, -1, 3), (0, 0, 1, 1))

    def test_a_leader_moves_with_its_text(self) -> None:
        dim = _radial("d", "View1", 0.1, 0.13)
        moved = lay._projected_segments(dim, 0.02, -0.01, OUTLINE)
        assert moved == [pytest.approx((0.11, 0.11, 0.12, 0.12))]


class TestOverlapReport:
    def test_every_kind_of_violation_is_named(self) -> None:
        on_obstacle = _hdim("a", "View1", 0.05, 0.17, 0.09, 0.10)
        twin = _hdim("b", "View1", 0.05, 0.17, 0.09, 0.10)
        problems = lay.find_overlaps(
            [on_obstacle, twin],
            {"View1": OUTLINE},
            sheet=(0.0, 0.095, 0.3, 0.3),
            obstacles={"title block": (0.10, 0.08, 0.12, 0.095)},
        )
        assert _kinds(problems) == {
            "on_obstacle",
            "outside_working_area",
            "text_on_text",
            "line_through_text",
        }

    def test_notes_are_checked_against_everything(self) -> None:
        dim = _hdim("d", "View1", 0.05, 0.17, 0.09, 0.10)
        notes = {
            "NOTES": (0.20, 0.20, 0.24, 0.21),
            "line 1": (0.21, 0.205, 0.25, 0.215),  # on NOTES
            "caption": (0.06, 0.12, 0.10, 0.13),  # on the view
            "rev": (0.26, 0.01, 0.28, 0.02),  # on the title block
            "stray": (0.29, 0.29, 0.35, 0.31),  # off the sheet
            "label": (0.105, 0.088, 0.115, 0.092),  # on the dimension
        }
        problems = lay.find_annotation_overlaps(
            notes,
            [dim],
            {"View1": OUTLINE},
            sheet=(0.0, 0.0, 0.3, 0.3),
            obstacles={"title block": (0.25, 0.0, 0.3, 0.05)},
        )
        assert _kinds(problems) == {
            "note_on_note",
            "note_on_view",
            "note_on_obstacle",
            "note_outside_working_area",
            "note_on_dimension",
        }


class TestPlanningChoices:
    def test_a_diameter_goes_to_a_free_corner(self) -> None:
        dims = [_radial("dia", "View1", 0.15, 0.16)]
        moves, unplaced = lay.plan_layout(dims, {"View1": OUTLINE})
        assert not unplaced
        moved = lay.shift_box(dims[0].text_box, *moves["dia"])
        assert not lay.box_overlap(moved, OUTLINE)
        assert moved[0] > OUTLINE[2] and moved[1] > OUTLINE[3]  # upper right

    def test_a_dimension_of_an_unknown_view_stays_put(self) -> None:
        dims = [_hdim("x", "Ghost", 0.05, 0.17, 0.12, 0.10)]
        assert lay.plan_layout(dims, {"View1": OUTLINE}) == ({}, ["x"])

    def test_no_room_on_the_sheet_leaves_it_unplaced(self) -> None:
        dims = [_hdim("w", "View1", 0.05, 0.17, 0.12, 0.10)]
        tight = (0.049, 0.099, 0.171, 0.171)  # the view fills the sheet
        assert lay.plan_layout(dims, {"View1": OUTLINE}, tight) == ({}, ["w"])

    def test_a_neighbouring_view_is_skipped_over(self) -> None:
        below = (0.05, 0.06, 0.17, 0.098)  # a second view right underneath
        dims = [_hdim("w", "View1", 0.05, 0.17, 0.12, 0.10)]
        moves, _ = lay.plan_layout(dims, {"View1": OUTLINE, "View2": below})
        moved = lay.shift_box(dims[0].text_box, *moves["w"])
        assert not lay.box_overlap(moved, below)

    def test_a_twin_dimension_takes_the_next_row(self) -> None:
        dims = [
            _hdim("a", "View1", 0.05, 0.17, 0.12, 0.10),
            _hdim("b", "View1", 0.05, 0.17, 0.12, 0.10),
        ]
        moves, unplaced = lay.plan_layout(dims, {"View1": OUTLINE})
        assert not unplaced
        assert abs(abs(moves["b"][1] - moves["a"][1]) - lay.ROW_PITCH) < 1e-9

    def test_rows_of_neighbouring_views_do_not_touch(self) -> None:
        upper = _hdim("a", "View1", 0.05, 0.17, 0.12, 0.10)  # goes below View1
        lower = _hdim("b", "View2", 0.05, 0.17, 0.07, 0.08)  # goes above View2
        outlines = {"View1": OUTLINE, "View2": (0.05, 0.02, 0.17, 0.08)}
        moves, unplaced = lay.plan_layout([upper, lower], outlines)
        assert not unplaced
        a = lay.shift_box(upper.text_box, *moves["a"])
        b = lay.shift_box(lower.text_box, *moves["b"])
        assert not lay.box_overlap(a, b, lay.TEXT_PADDING)

    def test_text_is_kept_off_a_placed_dimension_line(self) -> None:
        upper = _hdim("a", "View1", 0.05, 0.17, 0.12, 0.10)
        lower = _hdim("b", "View2", 0.05, 0.17, 0.07, 0.08)
        lower.text_box = (0.145, 0.0684, 0.155, 0.0716)  # right under a's line
        outlines = {"View1": OUTLINE, "View2": (0.05, 0.02, 0.17, 0.084)}
        moves, _ = lay.plan_layout([upper, lower], outlines)
        a_line_y = lay.shift_box(upper.text_box, *moves["a"])[1] + 0.0016
        b = lay.shift_box(lower.text_box, *moves["b"])
        assert not (b[1] <= a_line_y <= b[3])

    def test_dimension_lines_go_around_an_obstacle(self) -> None:
        dims = [_hdim("w", "View1", 0.05, 0.17, 0.12, 0.10)]
        marker = {"marker": (0.10, 0.0915, 0.102, 0.0925)}  # on row 1's line
        moves, _ = lay.plan_layout(dims, {"View1": OUTLINE}, None, marker)
        row = lay.shift_box(dims[0].text_box, *moves["w"])
        assert abs((OUTLINE[1] - (row[1] + row[3]) / 2) - lay.FIRST_OFFSET) > 1e-6


class TestLinesAcrossOtherViews:
    """A front view's height dimension must not stretch across the side view.

    Live on SW 2026 the planner parked it beyond the side view: its text was
    clear, but its extension lines ran straight across that view.
    """

    FRONT = (0.05, 0.10, 0.14, 0.145)
    SIDE = (0.15, 0.10, 0.20, 0.145)  # too close to fit a column in the gap

    def _height(self, x_line: float) -> lay.DimensionGeometry:
        return _vdim("height", "Front", 0.10, 0.145, x_line, self.FRONT[2])

    def test_a_line_across_another_view_is_reported(self) -> None:
        problems = lay.find_overlaps(
            [self._height(0.30)], {"Front": self.FRONT, "Side": self.SIDE}
        )
        assert {
            "dimension": "height",
            "conflicts_with": "Side",
            "kind": "line_through_view",
        } in problems

    def test_a_line_that_only_touches_a_view_is_fine(self) -> None:
        touching = [(0.10, 0.12, 0.15, 0.12)]  # ends on Side's left edge
        assert lay.crosses_other_view(touching, "Front", {"Side": self.SIDE}) is None
        assert lay.crosses_other_view(touching, "Side", {"Side": self.SIDE}) is None

    def test_the_planner_goes_round_the_other_view(self) -> None:
        dim = self._height(0.30)
        outlines = {"Front": self.FRONT, "Side": self.SIDE}

        moves, unplaced = lay.plan_layout([dim], outlines)

        assert not unplaced
        dx, dy = moves["height"]
        moved = lay.DimensionGeometry(
            key="height",
            view="Front",
            text_box=lay.shift_box(dim.text_box, dx, dy),
            position=dim.position,
            lines=lay._projected_segments(dim, dx, dy, self.FRONT),
        )
        assert lay.find_overlaps([moved], outlines) == []
        assert moved.text_box[2] < self.FRONT[0]  # the free left side
