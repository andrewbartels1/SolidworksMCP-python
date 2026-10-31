"""Check, and optionally re-run, the dimension layout of the open drawing.

Attaches to the drawing already open in SolidWorks (it closes nothing and
saves nothing), reads every dimension's real geometry and the view outlines,
and writes them with the overlap check to a JSON file. With ``--arrange`` it
then runs the layout passes and writes each pass's plan, moves and overlaps,
and the geometry read back afterwards. The JSON lets the planner be replayed
offline against what SolidWorks really drew.

Usage::

    python tests/scripts/layout_open_drawing.py
    python tests/scripts/layout_open_drawing.py --arrange
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

DEFAULT_OUT = Path("tests/.generated/layout_open_drawing.json")


def _snapshot(adapter: Any, drawing: Any, obstacles: dict, work_area: Any) -> dict:
    from solidworks_mcp.adapters.solidworks import dimension_layout as layout
    from solidworks_mcp.adapters.solidworks.io import _view_names

    names = _view_names(adapter, drawing)
    outlines, geometries, _ = adapter._collect_layout(drawing, names)
    return {
        "views": names,
        "outlines": outlines,
        "dimensions": [asdict(g) for g in geometries],
        "overlaps": layout.find_overlaps(geometries, outlines, work_area, obstacles),
    }


async def _run(arrange: bool, out: Path) -> int:
    from solidworks_mcp.adapters import sw_type_info
    from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
    from solidworks_mcp.adapters.solidworks.drawing_standard import (
        TITLE_BLOCK,
        WORK_AREA,
    )

    adapter = PyWin32Adapter({})
    await adapter.connect()
    model = adapter.swApp.ActiveDoc
    if model is None or adapter._get_attr_or_call(model, "GetType") != 3:
        print("[layout] the active document is not a drawing")
        return 1
    sw_type_info.flag_doc(model, 3)
    adapter.currentModel = model
    drawing = sw_type_info.flagged(model, "IDrawingDoc")
    # As the package's last step: clear of the title block and of every note
    # on the sheet (view captions, the NOTES block) as SolidWorks drew it.
    obstacles = {"title block": TITLE_BLOCK, **adapter._sheet_note_boxes(drawing)}
    report: dict[str, Any] = {
        "title": adapter._get_attr_or_call(model, "GetTitle"),
        "before": _snapshot(adapter, drawing, obstacles, WORK_AREA),
    }
    print(f"[layout] {report['title']}: {len(report['before']['overlaps'])} overlaps")
    for p in report["before"]["overlaps"]:
        print(f"  {p['dimension']} x {p['conflicts_with']} ({p['kind']})")
    if arrange:
        result = adapter._arrange_layout(None, obstacles, WORK_AREA)
        report["arrange"] = result
        report["after"] = _snapshot(adapter, drawing, obstacles, WORK_AREA)
        for t in result["trace"]:
            print(
                f"[layout] pass {t['pass']}: moved {t['moved']} of "
                f"{len(t['movable'])}, {len(t['overlaps'])} overlaps left"
            )
        for p in report["after"]["overlaps"]:
            print(f"  {p['dimension']} x {p['conflicts_with']} ({p['kind']})")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=list), encoding="utf-8")
    print(f"[layout] wrote {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arrange", action="store_true", help="run the layout")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    return asyncio.run(_run(args.arrange, args.out))


if __name__ == "__main__":
    raise SystemExit(main())
