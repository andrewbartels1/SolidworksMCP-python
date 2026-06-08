r"""Live end-to-end demo for assembly Pack-and-Go via native SolidWorks APIs.

Copies ``wall_marker_jig_assem.SLDASM`` (and all referenced parts) to a
self-contained output folder and updates every internal component reference so
the copy opens without any dependency on the original file locations.

The implementation avoids ``IModelDocExtension.GetPackAndGo()`` (which is
not reliably available from an external automation process) and instead
uses the documented ``ISldWorks.ReplaceReferencedDocument`` API to rewrite
each component path inside the copied assembly on disk -- achieving the same
result as the GUI Pack-and-Go without opening a dialog.

Steps executed:

1. Open the source assembly (or reuse it if already open).
2. Enumerate referenced components via ``GetDependencies2``.
3. ``shutil.copy2`` the assembly and every part into ``out/pack_and_go/``.
4. For each part call ``ReplaceReferencedDocument(target_asm, orig, target_part)``
   so the copied assembly's stored paths point into the output folder.
5. Save an isometric PNG preview next to the copies.

On success the script exits 0 and prints a JSON report.  Run with the project
virtualenv on a Windows box that already has SolidWorks open::

    .\.venv\Scripts\python.exe scripts\wifi_pack_and_go_demo.py

Output is written to ``out/pack_and_go/`` inside the repository root:

- ``wall_marker_jig_assem.SLDASM`` — copied assembly
- ``*.SLDPRT``                      — copied component parts
- ``assembly_preview.png``          — isometric PNG preview
- ``pack_and_go_report.json``       — JSON status report
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402

SOURCE = Path(r"C:\Users\andre\Downloads\wall_marker_jig_assem.SLDASM")
OUT_DIR = REPO_ROOT / "out" / "pack_and_go"


def _check(label: str, result: Any) -> None:
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    print(f"  OK  {label}")


async def build_pack_and_go(source: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    adapter = PyWin32Adapter({})
    print("Connecting to SolidWorks ...")
    await adapter.connect()

    try:
        # ------------------------------------------------------------------
        # Step 1: open the assembly (error 65536 = same-title doc already
        # open from a previous test run; close all and retry once).
        # ------------------------------------------------------------------
        def _open_asm():
            import pythoncom

            app = adapter.swApp
            vt = pythoncom.VT_BYREF | pythoncom.VT_I4
            from win32com.client import VARIANT

            err = VARIANT(vt, 0)
            warn = VARIANT(vt, 0)
            model = app.OpenDoc6(str(source), 2, 1, "", err, warn)
            if model is None and err.value == 65536:
                app.CloseAllDocuments(False)
                err = VARIANT(vt, 0)
                warn = VARIANT(vt, 0)
                model = app.OpenDoc6(str(source), 2, 1, "", err, warn)
            if model is None:
                raise RuntimeError(f"OpenDoc6 failed err={err.value} warn={warn.value}")
            from solidworks_mcp.adapters import sw_type_info

            sw_type_info.flag_doc(model, 2)
            adapter.currentModel = model
            return model

        open_result = adapter._handle_com_operation("open_asm", _open_asm)
        _check("open assembly", open_result)

        # ------------------------------------------------------------------
        # Step 2: enumerate referenced components.
        # ------------------------------------------------------------------
        def _get_deps():
            deps_raw = adapter.currentModel.GetDependencies2(True, True, False) or []
            return [
                Path(d)
                for d in deps_raw
                if isinstance(d, str)
                and d.lower().endswith((".sldprt", ".sldasm", ".slddrw"))
            ]

        deps_result = adapter._handle_com_operation("get_deps", _get_deps)
        _check("get_dependencies", deps_result)
        dep_paths: list[Path] = deps_result.data
        print(f"  {len(dep_paths)} component(s): {[p.name for p in dep_paths]}")

        # ------------------------------------------------------------------
        # Step 3: copy assembly + parts into out_dir.
        # ------------------------------------------------------------------
        target_asm = out_dir / source.name
        shutil.copy2(source, target_asm)
        for dep in dep_paths:
            shutil.copy2(dep, out_dir / dep.name)
        print(f"  OK  copy {1 + len(dep_paths)} file(s) -> {out_dir}")

        # ------------------------------------------------------------------
        # Step 4: rewrite component paths inside the COPY so it is
        # self-contained (does not depend on the original Downloads folder).
        # ------------------------------------------------------------------
        def _replace_refs():
            results: dict[str, bool] = {}
            for dep in dep_paths:
                ok = bool(
                    adapter.swApp._oleobj_.InvokeTypes(
                        56,
                        0,
                        1,
                        (11, 0),
                        ((8, 1), (8, 1), (8, 1)),
                        str(target_asm),
                        str(dep),
                        str(out_dir / dep.name),
                    )
                )
                results[dep.name] = ok
            return results

        refs_result = adapter._handle_com_operation("replace_refs", _replace_refs)
        _check("replace_references", refs_result)
        ref_map: dict[str, bool] = refs_result.data
        for name, ok in ref_map.items():
            print(f"    ref update {name}: {ok}")

        # ------------------------------------------------------------------
        # Step 5: isometric PNG preview saved next to the copies.
        # ------------------------------------------------------------------
        img_path = out_dir / "assembly_preview.png"
        img_result = await adapter.export_image(
            {
                "file_path": str(img_path),
                "format_type": "png",
                "width": 1600,
                "height": 1000,
                "view_orientation": "isometric",
            }
        )
        if img_result.is_success:
            print(f"  OK  preview -> {img_path}")
        else:
            print(f"  WARN preview skipped: {img_result.error}")

        copied = sorted(
            str(p)
            for p in out_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".sldasm", ".sldprt", ".slddrw"}
        )
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "source_assembly": str(source),
            "target_dir": str(out_dir),
            "status": "success",
            "method": "native_pack_and_go",
            "copied_file_count": len(copied),
            "copied_files": copied,
            "reference_updates": ref_map,
            "all_references_updated": all(ref_map.values()),
            "preview_image": str(img_path) if img_result.is_success else None,
        }

    finally:
        try:
            await adapter.disconnect()
            print("Disconnected.")
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN disconnect: {exc}")


def main() -> int:
    if not SOURCE.exists():
        print(f"ERROR: source not found: {SOURCE}")
        return 2
    try:
        report = asyncio.run(build_pack_and_go(SOURCE, OUT_DIR))
    except Exception:
        traceback.print_exc()
        return 1

    report_path = OUT_DIR / "pack_and_go_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nReport:")
    print(json.dumps(report, indent=2))
    print(f"\nReport written: {report_path}")
    return 0 if report.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
