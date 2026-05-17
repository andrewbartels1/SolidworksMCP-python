"""Yoke_male.sldprt — SolidWorks-as-Code tutorial script.

Demonstrates the full SoC checkpoint/rewind workflow with 3 save points.
Geometry derived from spec only; compare against the reference part at the end.

Reference (DO NOT open until the script completes):
  C:\\Users\\Public\\Documents\\SOLIDWORKS\\SOLIDWORKS 2026\\samples\\learn\\U-Joint\\Yoke_male.sldprt

Spec summary:
  Profile      : U-shape on Front plane, 80 mm wide × 100 mm tall
                 Body zone  Y =   0 → 40 mm  (40 mm body)
                 Arm zone   Y =  40 → 100 mm  (60 mm arms, 15 mm wide each)
                 Arm gap    X = -25 → +25     (50 mm clear span)
  Depth        : 38 mm symmetric extrude (±19 mm from Front plane)
  Pin bores    : ∅8 mm in each arm, centred at X = ±32.5 mm, Y = 70 mm
  Flange pad   : ∅60 mm × 3 mm, extruded downward from body base
  Flange holes : 4 × ∅4.2 mm on ∅50 mm bolt circle (M4 clearance pilots)
  Arm fillets  : 1 mm on arm top corners

Checkpoints:
  body-extrude  —  U-profile extruded, main mass established
  bore-cut      —  pin bores through both arms
  final         —  flange, mounting holes, and fillets complete

Interactive session replay
--------------------------
This script mirrors what the SoC exporter generates after an interactive
MCP session.  To regenerate it from a live session:

  from solidworks_mcp.agents.soc_exporter import export_session
  export_session("ujoint-yoke-male", "yoke_male_generated.py")

To rewind to a checkpoint if a step fails:

  from solidworks_mcp.agents.soc_rewind import rewind_to_checkpoint
  truncated = await rewind_to_checkpoint(
      adapter, session_id="ujoint-yoke-male", label="body-extrude",
      script_text=open("yoke_male_generated.py").read(),
  )

Run (requires SolidWorks + MCP server):
  .venv\\Scripts\\python.exe docs/getting-started/tutorial-parts/build_yoke_male_runbook.py

Verify by comparing the exported PNGs against the reference part above.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config

_OUT = Path(__file__).parent


def require(result: Any, label: str) -> Any:
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    return result.data


async def build_part() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
        # ── Part setup ──────────────────────────────────────────────────────
        require(await adapter.create_part(name="yoke_male"), "create_part")

        # ── Sketch 1: U-profile on Front plane ─────────────────────────────
        # 8 connected line segments form the U-shape.  SolidWorks extrudes the
        # enclosed region.  Origin at bottom-centre (bracket centreline).
        #
        #  X:  -40   -25       +25   +40
        #
        #       ├─────┐         ┌─────┤   Y=100  arm tops
        #       │     │         │     │
        #       │     │ 50 mm   │     │   Y=40→100  arms (60 mm tall, 15 mm wide)
        #       │     └─────────┘     │   Y=40   U-floor
        #       │                     │
        #       └─────────────────────┘   Y=0    body base

        require(await adapter.create_sketch("Front"), "create_sketch")

        line_1 = require(await adapter.add_line(-40.0, 0.0, -40.0, 100.0), "add_line")  # left edge
        line_2 = require(await adapter.add_line(-40.0, 100.0, -25.0, 100.0), "add_line")  # left arm top
        line_3 = require(await adapter.add_line(-25.0, 100.0, -25.0, 40.0), "add_line")  # left arm inner
        line_4 = require(await adapter.add_line(-25.0, 40.0, 25.0, 40.0), "add_line")  # U-floor
        line_5 = require(await adapter.add_line(25.0, 40.0, 25.0, 100.0), "add_line")  # right arm inner
        line_6 = require(await adapter.add_line(25.0, 100.0, 40.0, 100.0), "add_line")  # right arm top
        line_7 = require(await adapter.add_line(40.0, 100.0, 40.0, 0.0), "add_line")  # right edge
        line_8 = require(await adapter.add_line(40.0, 0.0, -40.0, 0.0), "add_line")  # base

        require(await adapter.exit_sketch(), "exit_sketch")

        # ── Extrude 38 mm symmetric ─────────────────────────────────────────
        require(
            await adapter.create_extrusion(
                ExtrusionParameters(
                    depth=38.0,
                    both_directions=True,
                )
            ),
            "create_extrusion",
        )

        # Checkpoint 1 — main U-body established
        _cp1 = str(_OUT / "yoke_male_cp1.sldprt")
        require(await adapter.save_file(_cp1), "save_file")

        # -- checkpoint ----------------------------------------------------
        # label:    body-extrude
        # file:     yoke_male_cp1.sldprt
        # records:  1-12
        # ----------------------------------------------------

        # ── Sketch 2: pin bores in both arms ───────────────────────────────
        # Two ∅8 mm through-holes cut in the arms (Z-direction, through all).
        # Arm mid-height : Y = (40 + 100) / 2 = 70 mm
        # Arm centrelines: X = ±(25 + 40) / 2 = ±32.5 mm (mid-width of each arm)

        require(await adapter.create_sketch("Front"), "create_sketch")

        circle_1 = require(await adapter.add_circle(-32.5, 70.0, 4.0), "add_circle")  # left arm bore
        circle_2 = require(await adapter.add_circle(32.5, 70.0, 4.0), "add_circle")  # right arm bore

        require(await adapter.exit_sketch(), "exit_sketch")

        require(
            await adapter.create_cut_extrude(ExtrusionParameters(through_all=True)),
            "create_cut_extrude",
        )

        # Checkpoint 2 — pin bores complete
        _cp2 = str(_OUT / "yoke_male_cp2.sldprt")
        require(await adapter.save_file(_cp2), "save_file")

        # -- checkpoint ----------------------------------------------------
        # label:    bore-cut
        # file:     yoke_male_cp2.sldprt
        # records:  13-18
        # ----------------------------------------------------

        # ── Sketch 3: flange pad on body base ──────────────────────────────
        # ∅60 mm circle at origin on the Front plane (body base, Y=0).
        # Extruded 3 mm downward (reverse_direction=True) to form the pad.
        # NOTE: a production script would select the actual bottom face;
        # the Front-plane approach works when the base aligns with Y=0.

        require(await adapter.create_sketch("Front"), "create_sketch")

        circle_3 = require(await adapter.add_circle(0.0, 0.0, 30.0), "add_circle")  # ∅60 mm pad

        require(await adapter.exit_sketch(), "exit_sketch")

        require(
            await adapter.create_extrusion(
                ExtrusionParameters(
                    depth=3.0,
                    reverse_direction=True,
                )
            ),
            "create_extrusion",
        )

        # ── Sketch 4: flange mounting holes ────────────────────────────────
        # 4 × ∅4.2 mm on ∅50 mm bolt circle (M4 clearance pilots).
        # Holes at 90° intervals: (±25, 0) and (0, ±25) in the Top-plane XZ frame.

        require(await adapter.create_sketch("Top"), "create_sketch")

        circle_4 = require(await adapter.add_circle(25.0, 0.0, 2.1), "add_circle")
        circle_5 = require(await adapter.add_circle(-25.0, 0.0, 2.1), "add_circle")
        circle_6 = require(await adapter.add_circle(0.0, 25.0, 2.1), "add_circle")
        circle_7 = require(await adapter.add_circle(0.0, -25.0, 2.1), "add_circle")

        require(await adapter.exit_sketch(), "exit_sketch")

        require(
            await adapter.create_cut_extrude(ExtrusionParameters(through_all=True)),
            "create_cut_extrude",
        )

        # ── Fillets: 1 mm on arm top corners ───────────────────────────────
        require(
            await adapter.add_fillet(
                radius=1.0,
                edge_names=["Edge<1>", "Edge<2>", "Edge<3>", "Edge<4>"],
            ),
            "add_fillet",
        )

        # Checkpoint 3 — final part complete
        _cp3 = str(_OUT / "yoke_male_final.sldprt")
        require(await adapter.save_file(_cp3), "save_file")

        # -- checkpoint ----------------------------------------------------
        # label:    final
        # file:     yoke_male_final.sldprt
        # records:  19-28
        # ----------------------------------------------------

        # ── Verification exports ────────────────────────────────────────────
        # Compare these against Yoke_male.sldprt AFTER the script runs.
        for view in ("isometric", "front", "top", "right"):
            require(
                await adapter.export_image(
                    {
                        "file_path": str(_OUT / f"yoke_male_{view}.png"),
                        "format_type": "png",
                        "width": 1600,
                        "height": 1000,
                        "view_orientation": view,
                    }
                ),
                f"export_image:{view}",
            )

    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    asyncio.run(build_part())
