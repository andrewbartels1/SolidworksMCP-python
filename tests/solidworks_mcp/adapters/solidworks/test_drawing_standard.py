"""Tests for the A3 standard layout maths."""

from __future__ import annotations

from solidworks_mcp.adapters.solidworks import dimension_layout as lay
from solidworks_mcp.adapters.solidworks import drawing_standard as std


class TestNotes:
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
