"""Finish the README demo from the plate and drawing already open in SolidWorks.

Picks up where ``tests/live/test_live_sw_readme_demo.py`` leaves the plate
drawing (PS-01) and runs the rest of the demo with the same steps and tool
calls, without remaking the plate:

1. save the open plate and its drawing into ``--out`` (a test's teardown may
   have deleted their files; the documents are still open);
2. lay the drawing's dimensions out clear of every note, as the drawing
   package's last step does, and add centre marks on the plan view;
3. GD&T: datums A, B, C and the position frame on the Ø5.5, found by value
   with ``list_model_dimensions``; save and export the PDF;
4. two plates mated 10 mm apart, checked with ``verify_model``;
5. the assembly drawing with its BOM.

Every step prints its evidence; set ``SW_DEMO_CAPTURE_DIR`` to capture frames
and the call transcript as the demo test does. Nothing is closed afterwards.

Usage::

    python tests/scripts/readme_demo_continue.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "tests" / ".generated" / "readme_demo"


def _open_document(listing: list[dict[str, Any]], kind: str, name: str) -> dict:
    """The open document of ``kind`` whose title contains ``name``."""
    for doc in listing:
        if doc["type"] == kind and name.lower() in str(doc["title"]).lower():
            return doc
    titles = ", ".join(f"{d['title']} ({d['type']})" for d in listing) or "none"
    raise SystemExit(f"[demo] no open {kind} named like {name!r}; open: {titles}")


def _require(result: Any, what: str) -> None:
    """Stop with the adapter's own error when a step fails."""
    if not result.is_success:
        raise SystemExit(f"[demo] {what} failed: {result.error}")


async def _activate(call: Any, adapter: Any, doc: dict[str, Any], kind: int) -> None:
    """Make ``doc`` the active document and check it really is."""
    reply = await call(
        "activate_document", {"title_or_path": doc["path"] or doc["title"]}
    )
    model = adapter.currentModel
    active = adapter._get_attr_or_call(model, "GetType") if model is not None else None
    print(f"[demo] activated {doc['title']}: {reply.get('message')}, type {active}")
    if active != kind:
        raise SystemExit(f"[demo] {doc['title']} is not the active document")


def _package(adapter: Any) -> dict[str, Any]:
    """What the demo reads from the drawing package's reply, read off the drawing.

    The generator names the views front, plan, side, iso in that order, and
    the sheet scale is the front view's.
    """
    from solidworks_mcp.adapters.solidworks.io import (
        _resolve_drawing_view,
        _sw_type_info,
        _view_names,
    )

    drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
    names = _view_names(adapter, drawing)
    roles = dict(zip(names, ("front", "plan", "side", "iso"), strict=False))
    front = _resolve_drawing_view(adapter, drawing, names[0])
    scale = float(front.ScaleDecimal)
    return {
        "data": {
            "views": {n: {"role": r} for n, r in roles.items()},
            "scale": f"{scale:g}:1",
        }
    }


async def _run(out: Path) -> int:
    sys.path.insert(0, str(REPO))
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
    from solidworks_mcp.adapters.solidworks.drawing_standard import (
        TITLE_BLOCK,
        WORK_AREA,
    )
    from solidworks_mcp.adapters.solidworks.io import _sw_type_info
    from solidworks_mcp.tools.file_management import register_file_management_tools
    from tests.live import test_live_sw_readme_demo as demo
    from tests.live.evidence import evidence

    adapter = PyWin32Adapter({})
    await adapter.connect()
    tools = await demo._tools(adapter)
    from fastmcp import FastMCP

    files = FastMCP("readme-demo-files")
    await register_file_management_tools(files, adapter, {})
    tools |= {t.name: t.fn for t in await files.list_tools()}
    call = demo._Session(tools, adapter)
    out.mkdir(parents=True, exist_ok=True)
    drawings = out / "drawings"
    drawings.mkdir(exist_ok=True)

    listing = (await adapter.list_open_documents()).data or []
    part = _open_document(listing, "Part", "Demo Plate")
    sheet = _open_document(listing, "Drawing", "PS-01")

    # 1. The plate, saved where the assembly can find it; its Ø dimension.
    print(
        f"[demo] open: {part['title']} ({part['path'] or 'no file'}), "
        f"{sheet['title']} ({sheet['path'] or 'no file'})"
    )
    await _activate(call, adapter, part, 1)
    plate = str(out / "Demo Plate.SLDPRT")
    _require(await adapter.save_file(plate), "saving the plate")
    hole_dim = await demo._hole_dimension(call, "Sketch1")

    # 2. The drawing: laid out clear of every note, centre marks on the plan.
    await _activate(call, adapter, sheet, 3)
    _require(await adapter.save_file(str(drawings / "PS-01.SLDDRW")), "saving PS-01")
    package = _package(adapter)
    drawing = _sw_type_info.flagged(adapter.currentModel, "IDrawingDoc")
    obstacles = {"title block": TITLE_BLOCK, **adapter._sheet_note_boxes(drawing)}
    layout = adapter._arrange_layout(None, obstacles, WORK_AREA)
    evidence(
        "step 3: the plate drawing, laid out clear of the view names and notes",
        {k: layout[k] for k in ("dimensions", "moved", "passes", "overlaps_after")}
        | {"remaining_overlaps": layout["remaining_overlaps"]},
    )
    assert layout["overlaps_after"] == 0, layout["remaining_overlaps"]
    plan_view = demo._role(package, "plan")
    marks = await call("auto_center_marks", {"view_name": plan_view})
    evidence(
        "step 3: centre marks on the holes",
        {"centre_marks_added": marks.get("center_marks_added")},
        call=f'auto_center_marks({{"view_name": "{plan_view}"}})',
    )

    # 3-5. GD&T, then the stack and its drawing: the demo test's own steps.
    await demo._gdt_and_save(call, adapter, package, hole_dim, drawings)
    await demo._stack_and_draw(call, adapter, plate, out, drawings, hole_dim)

    evidence(
        f"{len(call.calls)} tool calls, all successful",
        " -> ".join(c["tool"] for c in call.calls),
    )
    capture_dir = os.getenv("SW_DEMO_CAPTURE_DIR")
    if capture_dir:
        transcript = Path(capture_dir) / "plate_stack_continued_calls.json"
        transcript.write_text(json.dumps({"calls": call.calls}, indent=2), "utf-8")
    print(f"[demo] files in {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    return asyncio.run(_run(args.out.resolve()))


if __name__ == "__main__":
    raise SystemExit(main())
