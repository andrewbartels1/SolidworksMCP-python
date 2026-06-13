r"""Live end-to-end demo for all export format operations.

Exercises every export format backed by a real COM call in the
PyWin32 adapter:

    export_step  (.step)  — neutral CAD, preferred for manufacturing
    export_stl   (.stl)   — mesh triangles, required for 3D printing
    export_iges  (.igs)   — legacy neutral format, surface models
    export_image (.png)   — viewport screenshot

Note on PDF and DWG
-------------------
``export_pdf`` and ``export_dwg`` call ``SaveAs3`` with the file
extension driving format selection.  On SolidWorks 2026 this works
correctly for drawing documents (.slddrw) but produces an empty or
zero-byte file when called on a part or assembly.  They are included
here with a graceful failure path; a proper exercise of those tools
requires a drawing document (see ``create_drawing``).

Build sequence
--------------
1. 30 × 30 × 15 mm rectangular box (sketch + extrude).
2. Save the native .sldprt so SolidWorks knows the file path.
3. Export to STEP, STL, IGES.
4. Export PNG screenshot (isometric).
5. Attempt PDF and DWG exports; note outcome without failing the demo.
6. Print a file-size table for every artefact.

Run with the project virtualenv on a Windows box that has SolidWorks
open::

    .\.venv\Scripts\python.exe scripts\demo_export.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from solidworks_mcp.adapters.base import ExtrusionParameters  # noqa: E402
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402


def _check(label: str, result) -> None:
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    print(f"  OK  {label}")


def _kb(path: str) -> str:
    try:
        return f"{os.path.getsize(path) / 1024:.1f} KB"
    except OSError:
        return "(not found)"


async def run_export_demo(out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    adapter = PyWin32Adapter({})
    print("Connecting to SolidWorks ...")
    await adapter.connect()
    print(f"  Connected: {type(adapter.swApp).__name__}")

    artefacts: dict[str, str] = {}

    try:
        # ------------------------------------------------------------------
        # Build a simple 30x30x15 mm box.
        # ------------------------------------------------------------------
        part = await adapter.create_part()
        _check("create_part", part)
        print(f"  doc: {part.data.name}")

        sk = await adapter.create_sketch("Front")
        _check("create_sketch Front", sk)
        for x1, y1, x2, y2 in [
            (-15, -15,  15, -15),
            ( 15, -15,  15,  15),
            ( 15,  15, -15,  15),
            (-15,  15, -15, -15),
        ]:
            await adapter.add_line(x1, y1, x2, y2)
        _check("exit_sketch", await adapter.exit_sketch())

        boss = await adapter.create_extrusion(ExtrusionParameters(depth=15.0))
        _check("create_extrusion 15 mm", boss)

        # Save native so SolidWorks assigns a file path (required for SaveAs3).
        part_path = str((out_dir / "export_demo.SLDPRT").resolve())
        _check("save_file (native .sldprt)", await adapter.save_file(part_path))
        artefacts["native_sldprt"] = part_path

        # ------------------------------------------------------------------
        # export_step
        # ------------------------------------------------------------------
        print("\n-- export_step ---------------------------------------------")
        step_path = str((out_dir / "export_demo.step").resolve())
        r = await adapter.export_file(step_path, "step")
        _check("export_file step", r)
        artefacts["step"] = step_path
        print(f"       file: {step_path}  [{_kb(step_path)}]")

        # ------------------------------------------------------------------
        # export_stl
        # ------------------------------------------------------------------
        print("\n-- export_stl ----------------------------------------------")
        stl_path = str((out_dir / "export_demo.stl").resolve())
        r = await adapter.export_file(stl_path, "stl")
        _check("export_file stl", r)
        artefacts["stl"] = stl_path
        print(f"       file: {stl_path}  [{_kb(stl_path)}]")

        # ------------------------------------------------------------------
        # export_iges
        # ------------------------------------------------------------------
        print("\n-- export_iges ---------------------------------------------")
        iges_path = str((out_dir / "export_demo.igs").resolve())
        r = await adapter.export_file(iges_path, "iges")
        _check("export_file iges", r)
        artefacts["iges"] = iges_path
        print(f"       file: {iges_path}  [{_kb(iges_path)}]")

        # ------------------------------------------------------------------
        # export_image (PNG, isometric)
        # ------------------------------------------------------------------
        print("\n-- export_image (PNG) --------------------------------------")
        img_path = str((out_dir / "export_demo_isometric.png").resolve())
        r = await adapter.export_image(
            {
                "file_path": img_path,
                "format_type": "png",
                "width": 1600,
                "height": 1000,
                "view_orientation": "isometric",
            }
        )
        _check("export_image isometric png", r)
        artefacts["png_isometric"] = img_path
        print(f"       file: {img_path}  [{_kb(img_path)}]")

        # ------------------------------------------------------------------
        # export_pdf  (graceful — part-level PDF may be empty on some SW builds)
        # ------------------------------------------------------------------
        print("\n-- export_pdf (part-level, may be empty) -------------------")
        pdf_path = str((out_dir / "export_demo.pdf").resolve())
        r = await adapter.export_file(pdf_path, "pdf")
        if r.is_success and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            artefacts["pdf"] = pdf_path
            print(f"  OK  export_file pdf  [{_kb(pdf_path)}]")
        else:
            msg = r.error if not r.is_success else "zero-byte output"
            print(f"  --  export_file pdf: {msg}")
            print("       PDF export from a part works reliably only on .slddrw documents.")

        # ------------------------------------------------------------------
        # export_dwg  (graceful — same caveat as PDF)
        # ------------------------------------------------------------------
        print("\n-- export_dwg (part-level, may fail) -----------------------")
        dwg_path = str((out_dir / "export_demo.dwg").resolve())
        r = await adapter.export_file(dwg_path, "dwg")
        if r.is_success and os.path.exists(dwg_path) and os.path.getsize(dwg_path) > 0:
            artefacts["dwg"] = dwg_path
            print(f"  OK  export_file dwg  [{_kb(dwg_path)}]")
        else:
            msg = r.error if not r.is_success else "zero-byte output"
            print(f"  --  export_file dwg: {msg}")
            print("       DWG export from a part works reliably only on .slddrw documents.")

        return artefacts

    finally:
        try:
            await adapter.disconnect()
            print("\nDisconnected.")
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN disconnect: {exc}")
    return artefacts


def main() -> int:
    out_dir = REPO_ROOT / "out"
    try:
        artefacts = asyncio.run(run_export_demo(out_dir))
    except Exception:
        traceback.print_exc()
        return 1

    print("\n" + "=" * 55)
    print("ARTEFACTS")
    print("=" * 55)
    for key, path in artefacts.items():
        size = _kb(path)
        print(f"  {key:<20} {Path(path).name:<30} {size}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
