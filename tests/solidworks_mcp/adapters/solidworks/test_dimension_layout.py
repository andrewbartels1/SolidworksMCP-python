"""Tests for the overlap-free dimension layout and the A3 standard layout maths."""

from __future__ import annotations

import math

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

    def test_a_blocked_side_is_not_swapped_for_the_far_side(self) -> None:
        # Its extension lines start on the bottom edge; above the view they
        # would run across the whole part.
        dims = [_hdim("w", "View1", 0.05, 0.17, 0.12, 0.10)]
        below = (0.0, 0.0, 0.3, 0.1)  # everything below the view is blocked
        moves, unplaced = lay.plan_layout(
            dims, {"View1": OUTLINE}, None, {"caption": below}
        )
        assert (moves, unplaced) == ({}, ["w"])


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

    def test_a_leader_stays_on_its_feature(self) -> None:
        # The leader starts at the hole (0.09, 0.12) and reaches the moved
        # text's nearest edge; it does not move with the text.
        dim = _radial("d", "View1", 0.1, 0.13)
        moved = lay._projected_segments(dim, 0.02, -0.01, OUTLINE)
        assert moved == [pytest.approx((0.09, 0.12, 0.116, 0.12))]

    def test_a_leader_without_lines_has_no_anchor(self) -> None:
        dim = lay.DimensionGeometry("d", "View1", (0, 0, 0.01, 0.01), (0, 0))
        assert lay.leader_anchor(dim) is None
        assert lay._projected_segments(dim, 0.01, 0.0, OUTLINE) == []


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
    def test_a_diameter_steps_outward_from_its_hole(self) -> None:
        # The hole (0.14, 0.15) is up and right of the view's centre, so the
        # text goes up and right of the hole, clear of the view.
        dims = [_radial("dia", "View1", 0.15, 0.16)]
        moves, unplaced = lay.plan_layout(dims, {"View1": OUTLINE})
        assert not unplaced
        moved = lay.shift_box(dims[0].text_box, *moves["dia"])
        assert not lay.box_overlap(moved, OUTLINE)
        assert moved[0] > 0.14 and moved[1] > OUTLINE[3]

    def test_a_leader_keeps_clear_of_text_it_would_only_just_miss(self) -> None:
        # A text box 1 mm off the leader's first spot: an exact check passes
        # it, but SolidWorks draws the leader a little differently, so the
        # planner keeps 2 mm and moves on.
        hole = _radial("dia", "View1", 0.15, 0.16)
        first = lay._candidates(hole, OUTLINE)[0]
        box = lay.shift_box(hole.text_box, first[1], first[2])
        leader = lay._leader_to((0.14, 0.15), box)
        # Near the text end of the leader, well away from the hole it starts at.
        mx = leader[0] + 0.9 * (leader[2] - leader[0])
        my = leader[1] + 0.9 * (leader[3] - leader[1])
        dx, dy = leader[2] - leader[0], leader[3] - leader[1]
        length = (dx * dx + dy * dy) ** 0.5
        # A 1 mm square whose nearest corner is about 1 mm off the leader.
        cx, cy = mx - dy / length * 0.0018, my + dx / length * 0.0018
        near = _hdim("w", "View1", 0.05, 0.17, 0.12, 0.10)
        near.text_box = (cx - 0.0005, cy - 0.0005, cx + 0.0005, cy + 0.0005)
        assert not lay.segment_hits_box(leader, near.text_box)

        moves, unplaced = lay.plan_layout([hole, near], {"View1": OUTLINE}, fixed={"w"})

        assert not unplaced
        assert moves["dia"] != (first[1], first[2])
        chosen = lay.shift_box(hole.text_box, *moves["dia"])
        path = lay._leader_to((0.14, 0.15), chosen)
        assert not lay.segment_hits_box(
            path, lay._grown(near.text_box, lay.LEADER_CLEARANCE)
        )

    def test_a_leader_never_runs_through_another_dimensions_text(self) -> None:
        # A dimension's text sits on the up-right diagonal from the hole; the
        # leader takes another direction rather than crossing it.
        hole = _radial("dia", "View1", 0.15, 0.16)
        blocker = _hdim("w", "View1", 0.05, 0.17, 0.12, 0.10)
        blocker.text_box = (0.155, 0.168, 0.185, 0.2)
        moves, unplaced = lay.plan_layout(
            [hole, blocker], {"View1": OUTLINE}, fixed={"w"}
        )
        assert not unplaced and "w" not in moves
        box = lay.shift_box(hole.text_box, *moves["dia"])
        leader = lay._leader_to((0.14, 0.15), box)
        assert not lay.segment_hits_box(leader, blocker.text_box)

    def test_fixed_dimensions_stay_and_push_the_next_row_out(self) -> None:
        first = _hdim("a", "View1", 0.05, 0.17, 0.12, 0.10)
        row1 = OUTLINE[1] - lay.FIRST_OFFSET
        first.text_box = shift = lay.shift_box(first.text_box, 0.0, row1 - 0.12)
        second = _hdim("b", "View1", 0.06, 0.16, 0.12, 0.10)
        moves, _ = lay.plan_layout([first, second], {"View1": OUTLINE}, fixed={"a"})
        assert "a" not in moves
        row2 = lay.shift_box(second.text_box, *moves["b"])
        assert row2[3] < shift[1]  # below the fixed row, not on it

    def test_dimensions_that_do_not_touch_share_a_row(self) -> None:
        # The hole positions at each end of a plate go in the first row; the
        # overall length, whose line spans both, goes in the next one out.
        left = _hdim("left", "View1", 0.05, 0.07, 0.12, 0.10)
        right = _hdim("right", "View1", 0.15, 0.17, 0.12, 0.10)
        total = _hdim("total", "View1", 0.05, 0.17, 0.12, 0.10)
        moves, unplaced = lay.plan_layout([total, left, right], {"View1": OUTLINE})
        assert not unplaced
        y = {
            k: lay.shift_box(d.text_box, *moves[k])[1]
            for k, d in (("left", left), ("right", right), ("total", total))
        }
        assert y["left"] == pytest.approx(y["right"])
        assert y["total"] < y["left"]

    def test_a_fixed_dimension_of_an_unknown_view_is_still_an_obstacle(self) -> None:
        ghost = _hdim("g", "Ghost", 0.05, 0.17, 0.12, 0.10)
        moves, unplaced = lay.plan_layout([ghost], {"View1": OUTLINE}, fixed={"g"})
        assert moves == {} and unplaced == []

    def test_a_dimension_of_an_unknown_view_stays_put(self) -> None:
        dims = [_hdim("x", "Ghost", 0.05, 0.17, 0.12, 0.10)]
        assert lay.plan_layout(dims, {"View1": OUTLINE}) == ({}, ["x"])

    def test_no_room_on_the_sheet_leaves_it_unplaced(self) -> None:
        dims = [_hdim("w", "View1", 0.05, 0.17, 0.12, 0.10)]
        tight = (0.049, 0.099, 0.171, 0.171)  # the view fills the sheet
        assert lay.plan_layout(dims, {"View1": OUTLINE}, tight) == ({}, ["w"])

    def test_rows_stop_at_a_neighbouring_view(self) -> None:
        below = (0.05, 0.06, 0.17, 0.087)  # room for one row, not two
        dims = [
            _hdim("w", "View1", 0.05, 0.17, 0.12, 0.10),
            _hdim("x", "View1", 0.05, 0.17, 0.12, 0.10),
        ]
        moves, unplaced = lay.plan_layout(dims, {"View1": OUTLINE, "View2": below})
        assert list(moves) == ["w"] and unplaced == ["x"]
        assert not lay.box_overlap(lay.shift_box(dims[0].text_box, *moves["w"]), below)

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
        lower = _hdim("b", "View2", 0.05, 0.17, 0.06, 0.07)  # goes above View2
        outlines = {"View1": OUTLINE, "View2": (0.05, 0.02, 0.17, 0.07)}
        moves, unplaced = lay.plan_layout([upper, lower], outlines)
        assert not unplaced
        a = lay.shift_box(upper.text_box, *moves["a"])
        b = lay.shift_box(lower.text_box, *moves["b"])
        assert not lay.box_overlap(a, b, lay.TEXT_PADDING)

    def test_text_is_kept_off_a_placed_dimension_line(self) -> None:
        upper = _hdim("a", "View1", 0.05, 0.17, 0.12, 0.10)  # row 1 below View1
        lower = _hdim("b", "View2", 0.12, 0.16, 0.07, 0.084)  # row 1 above View2
        outlines = {"View1": OUTLINE, "View2": (0.12, 0.03, 0.16, 0.084)}
        moves, _ = lay.plan_layout([upper, lower], outlines)
        a_line_y = lay.shift_box(upper.text_box, *moves["a"])[1] + 0.0016
        b = lay.shift_box(lower.text_box, *moves.get("b", (0.0, 0.0)))
        assert not (b[1] <= a_line_y <= b[3])

    def test_columns_of_neighbouring_views_do_not_touch(self) -> None:
        left = _vdim("a", "View1", 0.10, 0.15, 0.07, 0.10)  # column right of View1
        right = _vdim("b", "View2", 0.10, 0.15, 0.15, 0.125)  # column left of View2
        outlines = {
            "View1": (0.05, 0.10, 0.10, 0.15),
            "View2": (0.125, 0.10, 0.175, 0.15),
        }
        moves, unplaced = lay.plan_layout([left, right], outlines)
        assert list(moves) == ["a"] and unplaced == ["b"]  # 25 mm: one column

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

    def test_it_is_brought_back_into_a_gap_that_fits(self) -> None:
        dim = self._height(0.30)
        side = (0.165, 0.10, 0.20, 0.145)  # 25 mm gap: one column fits
        outlines = {"Front": self.FRONT, "Side": side}

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
        assert self.FRONT[2] < moved.text_box[0] < moved.text_box[2] < side[0]

    def test_with_no_gap_it_is_not_sent_across_its_own_view(self) -> None:
        outlines = {"Front": self.FRONT, "Side": self.SIDE}

        assert lay.plan_layout([self._height(0.30)], outlines) == ({}, ["height"])


class TestOwnSide:
    """A dimension stays on the side of its view its extension lines start from.

    Live on SW 2026 the planner moved the top view's height from its left to
    its right, and both extension lines ran across the whole view.
    """

    def test_extension_lines_start_on_the_part(self) -> None:
        dim = _vdim("h", "View1", 0.10, 0.17, 0.11, 0.05)  # text inside the view
        assert lay.extension_origins(dim) == [0.05, 0.05]
        assert lay.extension_origins(_radial("d", "View1", 0.1, 0.1)) == []

    def test_a_line_across_its_own_view_is_reported(self) -> None:
        across = _vdim("h", "View1", 0.10, 0.17, 0.19, 0.05)  # left edge -> right
        problems = lay.find_overlaps([across], {"View1": OUTLINE})
        assert {
            "dimension": "h",
            "conflicts_with": "View1",
            "kind": "line_through_own_view",
        } in problems
        beside = _vdim("h", "View1", 0.10, 0.17, 0.03, 0.05)
        assert not lay.crosses_own_view(beside, OUTLINE)
        assert not lay.crosses_own_view(_radial("d", "View1", 0.1, 0.1), OUTLINE)

    def test_a_height_on_the_far_side_comes_back(self) -> None:
        across = _vdim("h", "View1", 0.10, 0.17, 0.19, 0.05)

        moves, unplaced = lay.plan_layout([across], {"View1": OUTLINE})

        assert not unplaced
        moved = _apply([across], moves)
        assert moved[0].text_box[2] < OUTLINE[0]
        assert lay.find_overlaps(moved, {"View1": OUTLINE}) == []


class TestInsideTheView:
    """A hole note (a leader with its GD&T frame) may sit inside the part."""

    def _plate(self) -> tuple[lay.DimensionGeometry, lay.DimensionGeometry]:
        # A 10 mm hole position from the left edge, and the hole's Ø leader.
        pos = _hdim("pos", "View1", 0.050, 0.065, 0.09, 0.105)
        hole = _radial("dia", "View1", 0.060, 0.095)
        hole.lines = [(0.0675, 0.1125, 0.070, 0.115)]  # anchor on the hole
        return pos, hole

    def test_feature_points_are_the_line_ends_inside_the_view(self) -> None:
        pos, hole = self._plate()
        points = lay.feature_points([pos, hole], "View1", OUTLINE, skip="dia")
        assert points == [(0.065, 0.105)]  # the hole centre the 10 starts from

    @pytest.mark.parametrize(
        ("box", "clear"),
        [
            ((0.09, 0.13, 0.12, 0.14), True),
            ((0.052, 0.13, 0.07, 0.14), False),  # too near the outline
            ((0.064, 0.109, 0.08, 0.115), False),  # on the hole
        ],
        ids=["clear", "near the edge", "near a feature"],
    )
    def test_clear_inside(self, box, clear) -> None:
        assert lay.clear_inside(box, OUTLINE, [(0.065, 0.105)]) is clear

    def test_the_note_is_planned_inside_near_its_hole(self) -> None:
        pos, hole = self._plate()
        hole.text_box = (0.0, 0.0, 0.03, 0.012)  # Ø text with its frame
        moves, unplaced = lay.plan_layout(
            [pos, hole], {"View1": OUTLINE}, inside_first={"dia"}
        )
        assert not unplaced
        box = lay.shift_box(hole.text_box, *moves["dia"])
        assert lay.clear_inside(box, OUTLINE, [(0.065, 0.105), (0.070, 0.115)])
        hole.text_box = box
        hole.lines = lay._projected_segments(hole, *moves["dia"], OUTLINE)
        pos.text_box = lay.shift_box(pos.text_box, *moves["pos"])
        pos.lines = lay._projected_segments(pos, *moves["pos"], OUTLINE)
        assert lay.find_overlaps([pos, hole], {"View1": OUTLINE}) == []

    def test_no_room_inside_falls_back_to_outside(self) -> None:
        pos, hole = self._plate()
        hole.text_box = (0.0, 0.0, 0.2, 0.012)  # wider than the view
        moves, unplaced = lay.plan_layout(
            [pos, hole], {"View1": OUTLINE}, inside_first={"dia"}
        )
        assert not unplaced
        box = lay.shift_box(hole.text_box, *moves["dia"])
        assert not lay.box_overlap(box, OUTLINE)

    def test_text_inside_is_still_on_the_view_unless_it_is_clear(self) -> None:
        pos, hole = self._plate()
        hole.text_box = (0.064, 0.109, 0.08, 0.115)  # on the hole
        kinds = {
            (p["dimension"], p["kind"])
            for p in lay.find_overlaps([pos, hole], {"View1": OUTLINE})
        }
        assert ("dia", "on_view_geometry") in kinds
        pos.text_box = (0.09, 0.13, 0.10, 0.135)  # a linear dimension's text
        kinds = {
            (p["dimension"], p["kind"])
            for p in lay.find_overlaps([pos], {"View1": OUTLINE})
        }
        assert ("pos", "on_view_geometry") in kinds

    def test_a_leader_without_lines_is_never_inside(self) -> None:
        bare = lay.DimensionGeometry(
            "x", "View1", (0.09, 0.13, 0.1, 0.135), (0.09, 0.13)
        )
        assert lay._leader_inside(bare, [bare], OUTLINE) is False


class TestAttachedBoxes:
    def test_a_frame_grows_its_dimensions_text_and_nothing_else(self) -> None:
        dia = _hdim("dia", "View1", 0.05, 0.17, 0.12, 0.10)
        other = _hdim("w", "View1", 0.05, 0.17, 0.09, 0.10)
        before = other.text_box
        lay.attach_boxes([dia, other], {"dia": (-0.01, -0.012, 0.02, -0.002)})
        x, y = dia.position
        assert dia.text_box == pytest.approx(
            (x - 0.01, y - 0.012, x + 0.02, y + 0.0016)
        )
        assert other.text_box == before


class TestShownLength:
    @pytest.mark.parametrize(
        ("text", "shown"),
        [("<MOD-DIAM>5.5", 4), ("100", 3), (" 10 ", 2), ("<MOD-DIAM><HOLE-DEPTH>3", 3)],
    )
    def test_each_code_is_one_symbol(self, text: str, shown: int) -> None:
        assert lay.shown_length(text) == shown


class TestTextBox:
    def test_level_text_runs_right_from_its_corner(self) -> None:
        assert lay.text_box(0.1, 0.2, 0.014, 0.0035, 0.0) == pytest.approx(
            (0.1, 0.2, 0.114, 0.2035)
        )

    def test_vertical_text_runs_up_and_lies_left_of_its_corner(self) -> None:
        # The live top view's "30.00": corner on the dimension line at x 22.9 mm.
        box = lay.text_box(0.0229, 0.1656, 0.0142, 0.0035, math.pi / 2)
        assert box == pytest.approx((0.0194, 0.1656, 0.0229, 0.1798))
