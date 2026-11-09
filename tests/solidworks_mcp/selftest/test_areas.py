"""The four areas call the right tools with the hand-calculated values."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.selftest import expected as ex
from solidworks_mcp.selftest.areas import (
    AREAS,
    AssemblyArea,
    Context,
    DrawingArea,
    ExportArea,
    PartArea,
)
from solidworks_mcp.selftest.results import Check, ToolFailed

from .caller_stub import CallerStub


def _verify(args: dict) -> dict:
    """verify_model passing every expectation it was given."""
    tolerances = {"relative_tolerance", "length_tolerance_mm"}
    return {
        "checks": [
            {
                "name": key,
                "expected": value,
                "actual": value,
                "tolerance": 0.0,
                "unit": "mm³" if key == "volume_mm3" else "",
                "passed": True,
            }
            for key, value in args.items()
            if key not in tolerances
        ]
    }


def _stub(**extra) -> CallerStub:
    sketches = iter(["Sketch1", "Sketch2", "Sketch3"])
    return CallerStub(
        {
            "create_sketch": lambda _a: {"sketch": {"name": next(sketches)}},
            "verify_model": _verify,
            "list_components": {"components": ["selftest_block-1", "selftest_pin-1"]},
            "list_drawing_views": {"count": 1},
            **extra,
        }
    )


def test_areas_run_in_the_designed_order() -> None:
    assert [a.name for a in AREAS] == ["part", "assembly", "drawing", "export"]


@pytest.mark.asyncio
async def test_part_builds_checks_and_saves_both_parts(tmp_path: Path) -> None:
    stub = _stub()
    ctx = Context(stub, tmp_path)
    checks: list[Check] = []

    await PartArea().run(ctx, checks)

    assert ctx.files == {
        "block": str(tmp_path / "selftest_block.SLDPRT"),
        "pin": str(tmp_path / "selftest_pin.SLDPRT"),
    }
    volumes = {c.name: c.expected for c in checks if c.name.endswith("volume_mm3")}
    assert volumes == {
        "block: volume_mm3": ex.BLOCK_VOLUME_MM3,
        "after the hole: volume_mm3": ex.HOLE_VOLUME_MM3,
        "after the fillet: volume_mm3": ex.FILLET_VOLUME_MM3,
        "pin: volume_mm3": ex.PIN_VOLUME_MM3,
    }
    assert len(checks) == 8 and all(c.passed for c in checks)
    cut = next(a for n, a, _ in stub.log if n == "create_cut_extrude")
    assert cut == {
        "sketch_name": "Sketch2",
        "depth": 10.0,
        "end_condition": "ThroughAllBoth",
    }
    verify = next(a for n, a, _ in stub.log if n == "verify_model")
    assert verify["relative_tolerance"] == ex.VOLUME_TOLERANCE


@pytest.mark.asyncio
async def test_assembly_mates_by_faces_and_checks_counts(tmp_path: Path) -> None:
    stub = _stub()
    ctx = Context(stub, tmp_path, {"block": "b.SLDPRT", "pin": "p.SLDPRT"})
    checks: list[Check] = []

    await AssemblyArea().run(ctx, checks)

    mates = [a for n, a, _ in stub.log if n == "add_mate"]
    assert [(m["mate_type"], m["face_a"], m["face_b"]) for m in mates] == [
        ("concentric", ex.HOLE_WALL_POINT, ex.PIN_SIDE_POINT),
        ("coincident", ex.BLOCK_BOTTOM_POINT, ex.PIN_BOTTOM_POINT),
    ]
    assert mates[0]["component_a"] == "selftest_block-1"
    assert [c.name for c in checks] == [
        "assembly: component_count",
        "assembly: mate_count",
        "assembly: no_interference",
    ]


@pytest.mark.asyncio
async def test_assembly_without_the_pin_component_is_a_tool_failure(
    tmp_path: Path,
) -> None:
    stub = _stub(list_components={"components": ["selftest_block-1"]})
    ctx = Context(stub, tmp_path, {"block": "b.SLDPRT", "pin": "p.SLDPRT"})

    with pytest.raises(ToolFailed, match="no component from selftest_pin"):
        await AssemblyArea().run(ctx, [])


@pytest.mark.asyncio
@pytest.mark.parametrize(("count", "passed"), [(1, True), (3, False)])
async def test_drawing_counts_its_views(tmp_path: Path, count, passed) -> None:
    stub = _stub(list_drawing_views={"count": count})
    checks: list[Check] = []

    await DrawingArea().run(Context(stub, tmp_path, {"block": "b.SLDPRT"}), checks)

    assert checks == [
        Check("drawing: view_count", 1, count, unit="view", passed=passed)
    ]
    view = next(a for n, a, _ in stub.log if n == "add_drawing_view")
    assert view == {"model_file": "b.SLDPRT", "view_type": "isometric"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("content", "size"), [(b"ISO-10303-21;", 13), (None, None)])
async def test_export_checks_the_file(tmp_path: Path, content, size) -> None:
    def export(args: dict) -> dict:
        if content is not None:
            Path(args["file_path"]).write_bytes(content)
        return {}

    stub = _stub(export_step=export)
    checks: list[Check] = []

    await ExportArea().run(Context(stub, tmp_path, {"block": "b.SLDPRT"}), checks)

    assert checks[0].measured == size
    assert checks[0].passed is (size is not None)
    assert stub.log[0][1] == {"title_or_path": "b.SLDPRT"}
