r"""Live end-to-end demo for model analysis and inspection operations.

Exercises every query/inspection operation that has a real COM
implementation (not a simulated stub):

    get_model_info, list_features, list_configurations,
    calculate_mass_properties, get_dimension, set_dimension

Also notes the three tools that are currently simulated and therefore
return canned data regardless of the open model:

    check_interference  — returns {"interference_found": False, "interferences": []}
    analyze_geometry    — returns {"findings": ["No issues found"]}
    get_material_properties — returns hardcoded "Steel, Plain Carbon"

These are intentionally skipped in this demo; the stubs are annotated in
``src/solidworks_mcp/tools/analysis.py`` with a "Future" comment.

Build sequence
--------------
1. 40 × 40 × 20 mm rectangular box (sketch + extrude).
2. Add a 20 mm-radius circle on the Front plane and apply a sketch
   dimension so there is at least one named parameter in the document.
3. Run each analysis operation and print the result.

Run with the project virtualenv on a Windows box that has SolidWorks
open::

    .\.venv\Scripts\python.exe scripts\demo_analysis.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from solidworks_mcp.adapters.base import ExtrusionParameters  # noqa: E402
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402


def _check(label: str, result) -> None:
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    print(f"  OK  {label}")


def _pretty(obj: Any, indent: int = 6) -> str:
    """Compact pretty-print for nested dicts/lists."""
    return json.dumps(obj, indent=2, default=str).replace("\n", f"\n{' ' * indent}")


async def run_analysis_demo(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    adapter = PyWin32Adapter({})
    print("Connecting to SolidWorks ...")
    await adapter.connect()
    print(f"  Connected: {type(adapter.swApp).__name__}")

    try:
        # ------------------------------------------------------------------
        # Build a simple 40x40x20 box so there is solid geometry to inspect.
        # ------------------------------------------------------------------
        part = await adapter.create_part()
        _check("create_part", part)
        print(f"  doc: {part.data.name}")

        sk1 = await adapter.create_sketch("Front")
        _check("create_sketch Front (box)", sk1)
        for x1, y1, x2, y2 in [
            (-20, -20,  20, -20),
            ( 20, -20,  20,  20),
            ( 20,  20, -20,  20),
            (-20,  20, -20, -20),
        ]:
            await adapter.add_line(x1, y1, x2, y2)
        _check("exit_sketch (box)", await adapter.exit_sketch())

        boss = await adapter.create_extrusion(ExtrusionParameters(depth=20.0))
        _check("create_extrusion 20 mm", boss)
        print(f"  feature: {boss.data.name}")

        # Add a second sketch with a circle + explicit dimension so there is
        # a named parameter "D1@Sketch2" (or similar) available for querying.
        sk2 = await adapter.create_sketch("Front")
        _check("create_sketch Front (circle)", sk2)
        circle = await adapter.add_circle(0.0, 0.0, 20.0)
        _check("add_circle R=20 mm", circle)

        # Dimension the circle radius (creates parameter "D1@Sketch2" on SW 2026)
        dim = await adapter.add_sketch_dimension(
            entity1=circle.data,
            entity2=None,
            dimension_type="radial",
            value=20.0,
        )
        _check("add_sketch_dimension R=20", dim)

        _check("exit_sketch (circle)", await adapter.exit_sketch())

        # Save so the parameter name is stable (and get_dimension can read it)
        part_path = (out_dir / "analysis_demo.SLDPRT").resolve()
        _check("save_file", await adapter.save_file(str(part_path)))

        # ------------------------------------------------------------------
        # 1. get_model_info
        # ------------------------------------------------------------------
        print("\n-- get_model_info ------------------------------------------")
        r = await adapter.get_model_info()
        _check("get_model_info", r)
        info = r.data
        print(f"      title        : {info.get('title')}")
        print(f"      type         : {info.get('type')}")
        print(f"      configuration: {info.get('configuration')}")
        print(f"      feature_count: {info.get('feature_count')}")
        print(f"      is_dirty     : {info.get('is_dirty')}")

        # ------------------------------------------------------------------
        # 2. list_features
        # ------------------------------------------------------------------
        print("\n-- list_features -------------------------------------------")
        r = await adapter.list_features()
        _check("list_features", r)
        features = r.data or []
        print(f"      {len(features)} features in tree:")
        for feat in features[:10]:
            name = feat.get("name", "?") if isinstance(feat, dict) else getattr(feat, "name", "?")
            ftype = feat.get("type", "?") if isinstance(feat, dict) else getattr(feat, "type", "?")
            print(f"        {ftype:<22} {name}")
        if len(features) > 10:
            print(f"        ... ({len(features) - 10} more)")

        # ------------------------------------------------------------------
        # 3. list_configurations
        # ------------------------------------------------------------------
        print("\n-- list_configurations -------------------------------------")
        r = await adapter.list_configurations()
        _check("list_configurations", r)
        configs = r.data or []
        print(f"      configurations: {configs}")

        # ------------------------------------------------------------------
        # 4. calculate_mass_properties
        # ------------------------------------------------------------------
        print("\n-- calculate_mass_properties --------------------------------")
        r = await adapter.get_mass_properties()
        _check("get_mass_properties", r)
        mp = r.data
        print(f"      volume      : {mp.volume:,.1f} mm³")
        print(f"      surface_area: {mp.surface_area:,.1f} mm²")
        print(f"      mass        : {mp.mass:.6f} kg  (no material assigned -> 0.0 expected)")
        com = mp.center_of_mass
        print(f"      center of mass: ({com[0]:.2f}, {com[1]:.2f}, {com[2]:.2f}) mm")
        print(f"      Ixx: {mp.moments_of_inertia['Ixx']:.4f}  Iyy: {mp.moments_of_inertia['Iyy']:.4f}  Izz: {mp.moments_of_inertia['Izz']:.4f}")

        # ------------------------------------------------------------------
        # 5. get_dimension / set_dimension
        #
        # SolidWorks names the first parameter in each sketch "D1@SketchN".
        # "D1@Sketch2" is the expected name for the radius dimension just
        # added.  Attempt the read; if the name differs in this install,
        # note it and skip the set step.
        # ------------------------------------------------------------------
        print("\n-- get_dimension / set_dimension ----------------------------")
        dim_name = f"D1@{sk2.data}"
        r_get = await adapter.get_dimension(dim_name)
        if r_get.is_success:
            orig = r_get.data
            print(f"  OK  get_dimension('{dim_name}') = {orig:.2f} mm")

            r_set = await adapter.set_dimension(dim_name, 25.0)
            if r_set.is_success:
                print(f"  OK  set_dimension('{dim_name}', 25.0)")
                r_verify = await adapter.get_dimension(dim_name)
                if r_verify.is_success:
                    print(f"  OK  verify after set: {r_verify.data:.2f} mm (expected 25.00)")
                else:
                    print(f"  --  post-set verify: {r_verify.error}")
            else:
                print(f"  --  set_dimension: {r_set.error}")
        else:
            print(f"  --  get_dimension('{dim_name}'): {r_get.error}")
            print(f"       (dimension name varies by SW version; covered by unit tests)")

        # ------------------------------------------------------------------
        # Simulated tools — noted but not exercised
        # ------------------------------------------------------------------
        print("\n-- simulated tools (noted, not exercised) -------------------")
        print("  --  check_interference   : returns canned data (no real COM call)")
        print("  --  analyze_geometry     : returns canned data (no real COM call)")
        print("  --  get_material_properties: returns hardcoded 'Steel, Plain Carbon'")
        print("       These stubs are annotated in tools/analysis.py (Future section).")

    finally:
        try:
            await adapter.close_model(save=False)
        except Exception:  # noqa: BLE001
            pass
        try:
            await adapter.disconnect()
            print("\nDisconnected.")
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN disconnect: {exc}")


def main() -> int:
    out_dir = REPO_ROOT / "out"
    try:
        asyncio.run(run_analysis_demo(out_dir))
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
