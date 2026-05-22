"""HOW-TO: SolidWorks-as-Code - Checkpoint, Restore, and Proceed

This script is a living tutorial for the SolidWorks MCP Python adapter.
It builds the Yoke Male U-joint component in three acts:

  Act 1 - Build the base features correctly up through the pin bore.
  Act 2 - Make an intentional mistake on the stub shaft, then use
           "open checkpoint" to restore to the last known-good state.
  Act 3 - Apply the correct stub shaft and bore, save, and export.

Run it with SolidWorks open:

    .venv\\Scripts\\python.exe docs/getting-started/tutorial-parts/build_yoke_male_tutorial.py

Key takeaway
------------
SolidWorks-as-Code (SoC) scripts are just Python.  When you make a mistake,
you don't need to undo 20 mouse clicks - you re-open the checkpoint file and
re-run only the corrected steps.  This is the same "checkpoint → experiment →
restore" loop that version control gives you for code.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "docs" / "getting-started" / "tutorial-parts"

# Three output files illustrate the three states.
CHECKPOINT_PART = ARTIFACT_DIR / "yoke_male_checkpoint_preStub.SLDPRT"
WRONG_PART = ARTIFACT_DIR / "yoke_male_wrong_stub.SLDPRT"
FINAL_PART = ARTIFACT_DIR / "yoke_male_v2_from_prompt.SLDPRT"
FINAL_IMAGE = ARTIFACT_DIR / "yoke_male_v2_from_prompt_isometric.png"


# ── Helpers ──────────────────────────────────────────────────────────────────

def require(result: Any, label: str) -> Any:
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    return result


def banner(text: str) -> None:
    line = "-" * len(text)
    print(f"\n{line}\n{text}\n{line}")


# ── Shared sketch helpers ─────────────────────────────────────────────────────

async def build_base_features(adapter: Any) -> None:
    """Steps 1-4: base cylinder, U-slot, arm gap, pin bore.

    These steps are correct in both Act 1 and Act 3.  Factoring them into a
    shared helper makes it easy to call them after restoring from a checkpoint.
    """

    # Step 1 - Base cylinder dia38.10mm on Top plane, 47.625mm tall
    print("  [1] Base cylinder - dia38.10mm x 47.625mm")
    require(await adapter.create_sketch("Top"), "create_sketch BaseCircle")
    require(await adapter.add_circle(0, 0, 19.050), "base circle r=19.050")
    require(await adapter.exit_sketch(), "exit_sketch BaseCircle")
    require(
        await adapter.create_extrusion(ExtrusionParameters(depth=47.625)),
        "BaseExtrude 47.625mm",
    )

    # Step 2 - U-slot cut on Front plane (XY), through-all-both in Z.
    # Profile: 5 lines + 3 arcs forming the U-shaped slot.
    print("  [2] U-slot cut - Front plane, through-all-both")
    require(await adapter.create_sketch("Front"), "create_sketch USlot")
    bottom_edge = require(
        await adapter.add_line(-19.050, -1.366, 19.050, -1.366), "bottom edge"
    )
    right_outer = require(
        await adapter.add_line(19.050, -1.366, 19.050, 29.210), "right outer"
    )
    arc1 = require(
        await adapter.add_arc(19.050, 19.685, 19.050, 29.210, 9.525, 19.685),
        "right arm tip arc",
    )
    right_inner = require(
        await adapter.add_line(9.525, 19.685, 9.525, 9.525), "right inner wall"
    )
    arc2 = require(
        await adapter.add_arc(0, 9.525, -9.525, 9.525, 9.525, 9.525),
        "U-slot bottom arc",
    )
    left_inner = require(
        await adapter.add_line(-9.525, 9.525, -9.525, 19.685), "left inner wall"
    )
    arc3 = require(
        await adapter.add_arc(-19.050, 19.685, -9.525, 19.685, -19.050, 29.210),
        "left arm tip arc",
    )
    left_outer = require(
        await adapter.add_line(-19.050, 29.210, -19.050, -1.366), "left outer"
    )
    xaxis = require(
        await adapter.add_centerline(-19.050, 0, 19.050, 0), "X-axis centerline"
    )
    require(
        await adapter.add_sketch_dimension(arc1.data, None, "radial", 9.525),
        "dim R9.525 right arm",
    )
    require(
        await adapter.add_sketch_dimension(arc2.data, None, "radial", 9.525),
        "dim R9.525 U-bottom",
    )
    require(
        await adapter.add_sketch_dimension(arc3.data, None, "radial", 9.525),
        "dim R9.525 left arm",
    )
    require(
        await adapter.add_sketch_constraint(right_outer.data, None, "fix"),
        "fix right outer",
    )
    require(
        await adapter.add_sketch_constraint(left_outer.data, None, "fix"),
        "fix left outer",
    )
    require(
        await adapter.add_sketch_constraint(arc2.data, xaxis.data, "tangent"),
        "arc2 tangent to X-axis",
    )
    require(
        await adapter.add_sketch_dimension(bottom_edge.data, None, "linear", 38.100),
        "dim width 38.100mm",
    )
    require(
        await adapter.add_sketch_dimension(right_inner.data, None, "linear", 10.160),
        "dim right inner 10.160mm",
    )
    require(
        await adapter.add_sketch_dimension(left_inner.data, None, "linear", 10.160),
        "dim left inner 10.160mm",
    )
    require(await adapter.exit_sketch(), "exit_sketch USlot")
    require(
        await adapter.create_cut_extrude(
            ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=True)
        ),
        "USlot cut through-all-both",
    )

    # Step 3 - Arm gap rectangular slot on Right plane (YZ), through-all-both in X.
    # Removes the centre region Z:±10.160mm, Y:-7.455..29.145mm.
    print("  [3] Arm gap cut - Right plane, through-all-both")
    require(await adapter.create_sketch("Right"), "create_sketch ArmGap")
    require(await adapter.add_line(-10.160, -7.455, 10.160, -7.455), "gap bottom")
    require(await adapter.add_line(10.160, -7.455, 10.160, 29.145), "gap right")
    require(await adapter.add_line(10.160, 29.145, -10.160, 29.145), "gap top")
    require(await adapter.add_line(-10.160, 29.145, -10.160, -7.455), "gap left")
    require(await adapter.exit_sketch(), "exit_sketch ArmGap")
    require(
        await adapter.create_cut_extrude(
            ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=True)
        ),
        "ArmGap cut through-all-both",
    )

    # Step 4 - Pin bore dia9.525mm on Front plane, through-all-both in Z.
    print("  [4] Pin bore - dia9.525mm, Front plane, through-all-both")
    require(await adapter.create_sketch("Front"), "create_sketch PinBore")
    require(await adapter.add_circle(0, 9.525, 4.7625), "pin bore r=4.7625mm")
    require(await adapter.exit_sketch(), "exit_sketch PinBore")
    require(
        await adapter.create_cut_extrude(
            ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=True)
        ),
        "PinBore cut through-all-both",
    )


async def build_part() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:

        # ── ACT 1: Build the base features ────────────────────────────────────
        banner("ACT 1 - Build base features (base cylinder, U-slot, arm gap, pin bore)")

        require(
            await adapter.create_part(name="yoke_male_checkpoint_preStub"),
            "create_part",
        )
        await build_base_features(adapter)

        # Save the checkpoint BEFORE touching the stub shaft.
        # This is our "known-good" save point.  If anything goes wrong in the
        # next step, we can restore to here with adapter.open_model(CHECKPOINT_PART).
        print(f"\n  [CHECKPOINT] Saving to: {CHECKPOINT_PART.name}")
        require(await adapter.save_file(str(CHECKPOINT_PART)), "save checkpoint")

        # ── ACT 2: Make an intentional mistake ────────────────────────────────
        banner("ACT 2 - Intentional mistake: stub shaft with wrong extrusion depth")

        # WRONG: We sketch the stub shaft (r=6.350mm) on the Top plane (Y=0) and
        # extrude only 19.050mm.  The resulting stub sits at Y=0..19.050mm, buried
        # inside the base cylinder body (Y=0..47.625mm) - it never protrudes above
        # the cylinder at all.  You would not see it in the final part.
        #
        # The correct depth from the Top plane is 66.675mm: the first 47.625mm
        # merges into the base cylinder, and only the remaining 19.050mm protrudes
        # above it as the visible stub shaft (Y=47.625..66.675mm).
        print("  [WRONG] Stub shaft - 19.050mm from Top plane (buried in base body!)")
        require(
            await adapter.create_sketch("Top"), "create_sketch StubShaft (wrong)"
        )
        require(await adapter.add_circle(0, 0, 6.350), "stub shaft circle")
        require(await adapter.exit_sketch(), "exit_sketch StubShaft (wrong)")
        require(
            await adapter.create_extrusion(ExtrusionParameters(depth=19.050)),
            "StubExtrude 19.050mm (WRONG - should be 66.675mm)",
        )

        # Save the wrong version so you can open it in SolidWorks to see the problem.
        print(f"  [WRONG] Saving wrong version to: {WRONG_PART.name}")
        require(await adapter.save_file(str(WRONG_PART)), "save wrong part")

        # ── ACT 3: Restore from checkpoint and fix ─────────────────────────────
        banner("ACT 3 - Restore checkpoint and apply the correct stub shaft")

        # RESTORE: Re-open the checkpoint file.  SolidWorks loads the part back
        # exactly as it was at the save point - four features, no stub shaft.
        # From here we proceed with the corrected extrusion depth.
        print(f"  [RESTORE] Reopening checkpoint: {CHECKPOINT_PART.name}")
        require(
            await adapter.open_model(str(CHECKPOINT_PART)),
            "restore checkpoint",
        )

        # The adapter now sees the checkpoint file as the active model.
        # Re-run only the corrected steps (stub shaft onwards).

        # Step 5 - Stub shaft dia12.70mm from Top plane, 66.675mm total depth.
        # Sketching on the Top plane (Y=0) and extruding 66.675mm gives identical
        # geometry to "sketch on Face<1> at Y=47.625mm and extrude 19.050mm":
        #   - For Y=0..47.625mm, the r=6.350mm column is fully contained inside
        #     the r=19.050mm base cylinder → the merge adds no visible material.
        #   - For Y=47.625..66.675mm, the column protrudes as the stub shaft.
        # Using the Top plane avoids coordinate-based face selection, which is
        # fragile after parametric cuts have modified the model topology.
        print("  [5] Stub shaft - dia12.70mm x 66.675mm from Top plane (correct)")
        require(await adapter.create_sketch("Top"), "create_sketch StubShaft")
        require(await adapter.add_circle(0, 0, 6.350), "stub shaft dia=12.70mm")
        require(await adapter.exit_sketch(), "exit_sketch StubShaft")
        require(
            await adapter.create_extrusion(ExtrusionParameters(depth=66.675)),
            "StubExtrude 66.675mm from Top",
        )

        # Step 6 - D-bore on top face of stub shaft (Y=66.675mm).
        # The stub shaft boss just created a fresh top face at Y=66.675mm.
        # That face IS reliably selectable by world coordinate (unlike the
        # original base-cylinder top face which had parametric-cut ancestry).
        print("  [6] Stub bore - D-profile on top of stub shaft (Y=66.675mm)")
        _create_sketch_on_face_y(adapter, 66.675)
        require(
            await adapter.add_arc(0, 0, 4.763, 4.200, 4.763, -4.200),
            "D-bore arc CCW long",
        )
        require(await adapter.add_line(4.763, -4.200, 4.763, 4.200), "keyway chord")
        require(await adapter.exit_sketch(), "exit_sketch StubBore")
        require(
            await adapter.create_cut_extrude(
                ExtrusionParameters(depth=0.0, end_condition="ThroughAll", both_directions=False)
            ),
            "StubBore ThroughAll into stub",
        )

        # Save and export the finished part.
        print(f"\n  [FINAL] Saving to: {FINAL_PART.name}")
        require(await adapter.save_file(str(FINAL_PART)), "save final")
        require(await adapter.open_model(str(FINAL_PART)), "reopen for screenshot")
        require(
            await adapter.export_image(
                {
                    "file_path": str(FINAL_IMAGE),
                    "format_type": "png",
                    "width": 1600,
                    "height": 1000,
                    "view_orientation": "isometric",
                }
            ),
            "export_image",
        )

        banner("DONE")
        print(f"  Checkpoint : {CHECKPOINT_PART}")
        print(f"  Wrong stub : {WRONG_PART}  (open in SolidWorks to see the buried stub)")
        print(f"  Final part : {FINAL_PART}")
        print(f"  Final image: {FINAL_IMAGE}")

    finally:
        await adapter.disconnect()


# ── Face-sketch helper ────────────────────────────────────────────────────────

def _create_sketch_on_face_y(adapter: Any, y_mm: float) -> str:
    """Select the flat horizontal face at world Y=y_mm and open a sketch on it.

    This works reliably for FRESH faces (e.g., the top of a newly extruded
    boss) because their topology is not entangled with prior parametric cuts.
    Clears the selection state and rebuilds the model before attempting to pick.

    Returns the sketch name string.
    """
    import pythoncom  # noqa: PLC0415
    import win32com.client as _win32  # noqa: PLC0415

    # Walk the adapter wrapper chain to reach the raw PyWin32Adapter.
    raw: Any = adapter
    visited: set[int] = set()
    while raw is not None and id(raw) not in visited:
        visited.add(id(raw))
        if hasattr(raw, "_handle_com_operation"):
            break
        raw = getattr(raw, "adapter", None)
    if raw is None or raw.currentModel is None:
        raise RuntimeError("No active model for face sketch")

    def _op() -> str:
        model = raw.currentModel
        y_m = y_mm / 1000.0
        null_callout = _win32.VARIANT(pythoncom.VT_DISPATCH, None)

        try:
            model.ClearSelection2(True)
        except Exception:
            pass
        try:
            model.ForceRebuild3(True)
        except Exception:
            pass

        candidate_xz = [
            (0.0, 0.0), (0.005, 0.0), (-0.005, 0.0),
            (0.0, 0.005), (0.0, -0.005), (0.008, 0.008),
            (0.010, 0.0), (0.0, 0.010), (0.015, 0.015),
        ]
        selected = False
        for cx, cz in candidate_xz:
            for sel_fn in (
                lambda cx=cx, cz=cz: model.Extension.SelectByID2(
                    "", "FACE", cx, y_m, cz, False, 0, null_callout, 0
                ),
                lambda cx=cx, cz=cz: model.SelectByID2(
                    "", "FACE", cx, y_m, cz, False, 0, null_callout, 0
                ),
            ):
                try:
                    selected = bool(sel_fn())
                except Exception:
                    selected = False
                if selected:
                    break
            if selected:
                break

        if not selected:
            raise RuntimeError(
                f"SelectByID2 FACE at Y={y_mm}mm returned False for all candidate points"
            )

        raw.currentSketchManager = model.SketchManager
        raw._reset_sketch_entity_registry()
        try:
            sketch = raw.currentSketchManager.InsertSketch(True)
        except Exception:
            sketch = raw.currentSketchManager.InsertSketch()
        raw.currentSketch = sketch
        raw._sketch_count += 1
        name = str(getattr(sketch, "Name", None) or f"Sketch_{raw._sketch_count}")
        raw._last_sketch_name = name
        return name

    result = raw._handle_com_operation(f"create_sketch_on_face_y{y_mm}", _op)
    if not result.is_success:
        raise RuntimeError(f"create_sketch_on_face_y({y_mm}) failed: {result.error}")
    return str(result.data)


if __name__ == "__main__":
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.run(build_part())
