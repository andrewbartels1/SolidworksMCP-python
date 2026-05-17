r"""Live end-to-end demo for all nine sketch operations.

Builds a single decorative-plate part that exercises every method delivered
under upstream issue #5 / fork issue #1:

    add_spline, add_arc, add_centerline, add_polygon, add_ellipse,
    sketch_linear_pattern, sketch_circular_pattern, sketch_mirror,
    sketch_offset

Layout (all sketches on the Front plane, X horizontal, Y vertical, mm):

* Base plate 240 x 160 x 10 (boss-extrude from a closed rectangle drawn with
  ``add_line`` x 4).  Issue #1 itself does not deliver cut/feature surgery —
  this single solid body is just stage dressing so the decorative sketch is
  rendered against something physical in the screenshot.
* Decorative sketch on the same Front plane, kept un-extruded so the
  screenshot shows the geometry directly.  Contents:

  - ``add_polygon`` + ``sketch_linear_pattern`` -> hexagon row along +X
  - ``add_ellipse`` + ``sketch_circular_pattern`` -> ellipse rosette around origin
  - ``add_centerline`` + ``add_arc`` + ``add_spline`` + ``sketch_mirror`` ->
    arc/spline pair mirrored across a horizontal centerline
  - ``sketch_offset`` -> arc offset 3 mm outward

On success the script saves the resulting part and an isometric PNG to
``out/`` and exits 0.  Run with the project virtualenv on a Windows box that
already has SolidWorks open::

    .\.venv\Scripts\python.exe scripts\demo_sketches.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from solidworks_mcp.adapters.base import ExtrusionParameters  # noqa: E402
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402


def _check(label: str, result) -> None:
    """Raise with the COM error attached when an adapter result is not success."""
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    print(f"  OK  {label}")


async def build_demo_part(out_dir: Path) -> dict[str, str]:
    """Build the demo part end-to-end and return artefact paths."""
    out_dir.mkdir(parents=True, exist_ok=True)

    adapter = PyWin32Adapter({})
    print("Connecting to SolidWorks ...")
    await adapter.connect()
    print(f"Connected: swApp={type(adapter.swApp).__name__}")

    try:
        # ------------------------------------------------------------------
        # Document
        # ------------------------------------------------------------------
        part = await adapter.create_part()
        _check("create_part", part)
        print(f"  doc: {part.data.name}")

        # ------------------------------------------------------------------
        # Feature 1: base plate -- 240 x 160 mm, 10 mm thick
        # ------------------------------------------------------------------
        sk = await adapter.create_sketch("Front")
        _check("create_sketch Front (base)", sk)
        for x1, y1, x2, y2, label in (
            (-120, -80, 120, -80, "add_line bottom"),
            (120, -80, 120, 80, "add_line right"),
            (120, 80, -120, 80, "add_line top"),
            (-120, 80, -120, -80, "add_line left"),
        ):
            _check(label, await adapter.add_line(x1, y1, x2, y2))
        _check("exit_sketch (base)", await adapter.exit_sketch())
        _check(
            "create_extrusion 10 mm",
            await adapter.create_extrusion(ExtrusionParameters(depth=10.0)),
        )

        # ------------------------------------------------------------------
        # Feature 2: single decorative sketch on the same Front plane that
        # exercises every one of the nine sketch operations.  Kept
        # un-extruded so the wireframe shows up cleanly against the base
        # body in the screenshot.
        # ------------------------------------------------------------------
        sk = await adapter.create_sketch("Front")
        _check("create_sketch Front (decorative)", sk)

        # ---- add_polygon + sketch_linear_pattern (hex row, top half) ----
        hex_seed = await adapter.add_polygon(
            center_x=-90.0, center_y=55.0, radius=6.0, sides=6
        )
        _check("add_polygon (hex seed)", hex_seed)
        _check(
            "sketch_linear_pattern (10 hexagons across +X)",
            await adapter.sketch_linear_pattern(
                entities=[hex_seed.data],
                direction_x=1.0,
                direction_y=0.0,
                spacing=20.0,
                count=10,
            ),
        )

        # ---- add_ellipse + sketch_circular_pattern (rosette around origin) ----
        ell_seed = await adapter.add_ellipse(
            center_x=42.0, center_y=0.0, major_axis=14.0, minor_axis=6.0
        )
        _check("add_ellipse (rosette seed at +X)", ell_seed)
        _check(
            "sketch_circular_pattern (8x360 around origin)",
            await adapter.sketch_circular_pattern(
                entities=[ell_seed.data],
                angle=360.0,
                count=8,
            ),
        )

        # ---- add_centerline + add_arc + add_spline + sketch_mirror + sketch_offset ----
        # Horizontal centerline at y=-50 acts as the mirror axis for the
        # arc/spline band below it.  After mirroring, the arc is offset 3mm
        # outward to create a parallel decorative band on the lower edge.
        cl = await adapter.add_centerline(-90.0, -50.0, 90.0, -50.0)
        _check("add_centerline (mirror axis y=-50)", cl)

        arc = await adapter.add_arc(
            center_x=-50.0,
            center_y=-40.0,
            start_x=-70.0,
            start_y=-40.0,
            end_x=-30.0,
            end_y=-40.0,
        )
        _check("add_arc (above centerline)", arc)

        spl = await adapter.add_spline(
            points=[
                {"x": -10.0, "y": -45.0},
                {"x": 10.0, "y": -32.0},
                {"x": 30.0, "y": -45.0},
                {"x": 50.0, "y": -32.0},
                {"x": 70.0, "y": -45.0},
            ]
        )
        _check("add_spline (5-point curve above centerline)", spl)

        _check(
            "sketch_mirror (arc + spline across centerline)",
            await adapter.sketch_mirror(
                entities=[arc.data, spl.data], mirror_line=cl.data
            ),
        )

        _check(
            "sketch_offset (arc outward 3 mm)",
            await adapter.sketch_offset(
                entities=[arc.data], offset_distance=3.0, reverse_direction=False
            ),
        )

        _check("exit_sketch (decorative)", await adapter.exit_sketch())

        # ------------------------------------------------------------------
        # Persist + screenshot — both promised by the script docstring and
        # the PR test plan, so a failure here is a real demo failure, not
        # a warning.  ``_check`` raises which propagates back to ``main()``
        # and returns a non-zero exit code.
        # ------------------------------------------------------------------
        part_path = (out_dir / "sketch_demo.SLDPRT").resolve()
        _check(f"save_file -> {part_path}", await adapter.save_file(str(part_path)))

        img_path = (out_dir / "sketch_demo.png").resolve()
        _check(
            f"export_image -> {img_path}",
            await adapter.export_image(
                {
                    "file_path": str(img_path),
                    "format_type": "png",
                    "width": 1600,
                    "height": 1000,
                    "view_orientation": "isometric",
                }
            ),
        )

        return {
            "part": str(part_path),
            "screenshot": str(img_path),
        }
    finally:
        try:
            await adapter.disconnect()
            print("Disconnected.")
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN disconnect failed: {exc}")


def main() -> int:
    out_dir = REPO_ROOT / "out"
    try:
        artefacts = asyncio.run(build_demo_part(out_dir))
    except Exception:
        traceback.print_exc()
        return 1
    print("\nDemo artefacts:")
    for key, value in artefacts.items():
        print(f"  {key}: {value or '(skipped)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
