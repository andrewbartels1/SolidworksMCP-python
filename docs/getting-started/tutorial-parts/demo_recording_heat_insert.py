r"""Recording-friendly build of the M4 heat-set-insert coupon.

Designed to be screen-recorded: it first prints the natural-language prompt
that produced this script, then prints its own source code, then waits for
you to press Enter (switch to SolidWorks during that pause), then builds the
part one step at a time through the REAL registered MCP tools -- with a
visible pause between every step so each feature appears distinctly on
screen instead of flashing by all at once.

Run:
    .\.venv\Scripts\python.exe demo_recording_heat_insert.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------
# Recording pacing -- tune these for your recording.
# --------------------------------------------------------------------------
STEP_DELAY_SECONDS = 2.5  # pause after each build step, so it reads on camera
SWITCH_WAIT_MESSAGE = (
    "\nPress ENTER when you're ready -- switch to your SolidWorks window "
    "now, then hit Enter and don't touch the mouse/keyboard again until it's done.\n"
)

PROMPT_TEXT = """\
Build an M4 heat-set-insert mounting coupon in SolidWorks using the MCP
tools: a 30x30x15mm rectangular block, a centered Ø5.5mm x 6mm deep hole for
the insert, a 0.5mm chamfer on the top face (the one the block was sketched
on), and a 1mm fillet on the *other* largest face -- the bottom, which
doesn't touch the Top plane. Use the real registered MCP tools for every
step, not raw COM calls.
"""

REPO_ROOT = Path(r"C:\Users\andre\dev\SolidworksMCP-python")
sys.path.insert(0, str(REPO_ROOT / "src"))

from fastmcp import FastMCP  # noqa: E402

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402
from solidworks_mcp.tools.file_management import (  # noqa: E402
    ListFeaturesInput,
    register_file_management_tools,
)
from solidworks_mcp.tools.modeling import (  # noqa: E402
    AddChamferInput,
    AddFilletInput,
    CreateCutExtrudeInput,
    CreateExtrusionInput,
    CreatePartInput,
    register_modeling_tools,
)
from solidworks_mcp.tools.sketching import (  # noqa: E402
    AddCircleInput,
    AddDimensionInput,
    AddLineInput,
    CreateSketchInput,
    register_sketching_tools,
)

BLOCK_SIZE = 30.0
BLOCK_HEIGHT = 15.0
HOLE_DIAMETER = 5.5
HOLE_DEPTH = 6.0
HOLE_CENTER = BLOCK_SIZE / 2.0


def _show_prompt_and_source() -> None:
    print("=" * 72)
    print("PROMPT (given to Claude):")
    print("-" * 72)
    print(PROMPT_TEXT)
    print("=" * 72)
    print(f"GENERATED SCRIPT: {Path(__file__).name}")
    print("-" * 72)
    print(Path(__file__).read_text(encoding="utf-8"))
    print("=" * 72)


def _pause(label: str) -> None:
    print(f"  ... ({label}, {STEP_DELAY_SECONDS:.1f}s) ...")
    time.sleep(STEP_DELAY_SECONDS)


def _check(label: str, response: dict) -> None:
    status = response.get("status")
    ok = status == "success"
    print(f"  {'OK ' if ok else 'FAIL'} {label}: {response.get('message')}")
    if not ok:
        raise RuntimeError(f"{label} failed: {response}")


async def build() -> None:
    print("\nConnecting to SolidWorks...")
    adapter = PyWin32Adapter({})
    await adapter.connect()
    print(f"  Connected: swApp={type(adapter.swApp).__name__}")

    mcp = FastMCP("recording-demo")
    config: dict = {}
    await register_modeling_tools(mcp, adapter, config)
    await register_sketching_tools(mcp, adapter, config)
    await register_file_management_tools(mcp, adapter, config)
    tools = {t.name: t.fn for t in await mcp.list_tools()}

    try:
        print("\nStep 1/9: create_part")
        _check("create_part", await tools["create_part"](CreatePartInput(name="heat_insert_demo")))
        _pause("new part created")

        print("\nStep 2/9: sketch the 30x30mm block profile on the Top plane")
        _check("create_sketch", await tools["create_sketch"](CreateSketchInput(plane="Top")))
        bottom = await tools["add_line"](AddLineInput(x1=0, y1=0, x2=BLOCK_SIZE, y2=0))
        right = await tools["add_line"](AddLineInput(x1=BLOCK_SIZE, y1=0, x2=BLOCK_SIZE, y2=BLOCK_SIZE))
        await tools["add_line"](AddLineInput(x1=BLOCK_SIZE, y1=BLOCK_SIZE, x2=0, y2=BLOCK_SIZE))
        left = await tools["add_line"](AddLineInput(x1=0, y1=BLOCK_SIZE, x2=0, y2=0))
        await tools["add_sketch_dimension"](
            AddDimensionInput(entity1=bottom["line"]["id"], dimension_type="linear", value=BLOCK_SIZE)
        )
        await tools["add_sketch_dimension"](
            AddDimensionInput(entity1=left["line"]["id"], dimension_type="linear", value=BLOCK_SIZE)
        )
        _check("exit_sketch", await tools["exit_sketch"]())
        _pause("block profile sketched")

        print(f"\nStep 3/9: extrude the block {BLOCK_HEIGHT}mm")
        _check(
            "create_extrusion",
            await tools["create_extrusion"](CreateExtrusionInput(depth=BLOCK_HEIGHT, sketch_name="Sketch1")),
        )
        _pause("block extruded")

        print(f"\nStep 4/9: sketch the {HOLE_DIAMETER}mm diameter hole")
        _check("create_sketch", await tools["create_sketch"](CreateSketchInput(plane="Top")))
        circle = await tools["add_circle"](
            AddCircleInput(center_x=HOLE_CENTER, center_y=HOLE_CENTER, radius=HOLE_DIAMETER / 2)
        )
        await tools["add_sketch_dimension"](
            AddDimensionInput(entity1=circle["circle"]["id"], dimension_type="diameter", value=HOLE_DIAMETER)
        )
        _check("exit_sketch", await tools["exit_sketch"]())
        _pause("hole profile sketched")

        features_before_cut = await tools["list_features"](ListFeaturesInput())
        sketch_names = [f["name"] for f in features_before_cut["features"] if f.get("type") == "ProfileFeature"]
        hole_sketch_name = [n for n in sketch_names if n != "Sketch1"][0]

        print(f"\nStep 5/9: cut the hole {HOLE_DEPTH}mm deep")
        _check(
            "create_cut_extrude",
            await tools["create_cut_extrude"](CreateCutExtrudeInput(depth=HOLE_DEPTH, sketch_name=hole_sketch_name)),
        )
        _pause("hole cut")

        print("\nStep 6/9: chamfer the top face (0.5mm) -- hole rim + outer edges")
        _check(
            "add_chamfer",
            await tools["add_chamfer"](AddChamferInput(distance=0.5, edge_names=["face:0.005,0.005,0.0"])),
        )
        _pause("top face chamfered")

        print("\nStep 7/9: fillet the bottom face (1mm) -- the other largest face")
        _check(
            "add_fillet",
            await tools["add_fillet"](
                AddFilletInput(radius=1.0, edge_names=[f"face:0.005,0.005,-{BLOCK_HEIGHT / 1000.0}"])
            ),
        )
        _pause("bottom face filleted")

        print("\nStep 8/9: final feature tree")
        final = await tools["list_features"](ListFeaturesInput())
        for f in final["features"][:8]:
            print(f"    - {f['name']} ({f.get('type')})")
        _pause("done")

        print("\nStep 9/9: done -- switch back to SolidWorks to admire it")

    finally:
        await adapter.disconnect()


def main() -> None:
    _show_prompt_and_source()
    input(SWITCH_WAIT_MESSAGE)
    asyncio.run(build())


if __name__ == "__main__":
    main()
