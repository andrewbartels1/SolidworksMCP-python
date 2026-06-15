r"""Live end-to-end demo for assembly Pack-and-Go via the ``pack_and_go_assembly`` MCP tool.

Copies ``wall_marker_jig_assem.SLDASM`` (and all referenced parts) to a
self-contained output folder and updates every internal component reference so
the copy opens without any dependency on the original file locations.

This script exercises the same code path as the MCP tool ``pack_and_go_assembly``
by calling ``adapter.pack_and_go_assembly()`` directly — the same underlying
method that the registered FastMCP tool invokes.  It is intentionally written
in the same style as ``demo_sketches.py`` and ``demo_sweep_loft.py``.

Run with the project virtualenv on a Windows box that already has SolidWorks open::

    .\.venv\Scripts\python.exe scripts\wifi_pack_and_go_demo.py

Output is written to ``out/pack_and_go/`` inside the repository root:

- ``wall_marker_jig_assem.SLDASM`` — copied assembly
- ``*.SLDPRT``                      — copied component parts
- ``assembly_preview.png``          — isometric PNG preview
- ``pack_and_go_report.json``       — JSON status report

MCP tool equivalent (what an LLM would call)::

    pack_and_go_assembly({
        "source_path": r"C:\Users\andre\Downloads\wall_marker_jig_assem.SLDASM",
        "target_dir":  r"<repo>\out\pack_and_go",
        "export_preview": true
    })
"""

from __future__ import annotations

import asyncio
import json
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
        # Step 1-4: open, enumerate deps, copy, rewrite refs — all via the adapter method
        result = await adapter.pack_and_go_assembly(
            source_path=str(source),
            target_dir=str(out_dir),
        )
        _check("pack_and_go_assembly", result)
        print(f"  {len(result.data['copied_files'])} file(s) copied -> {out_dir}")
        for src, status in zip(result.data["source_files"], result.data["save_statuses"], strict=False):
            print(f"    {'OK' if status == 0 else 'FAIL'} {src}")

        # Step 5: isometric PNG preview
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

        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": "success",
            "method": "native_pack_and_go",
            **result.data,
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
