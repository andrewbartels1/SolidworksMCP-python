"""U-Bracket from runbook spec — SolidWorks-as-Code tutorial script.

Geometry derived entirely from the design spec in the runbook (no part file used).
After this script runs, compare the exported images against
  C:\\Users\\Public\\Documents\\SOLIDWORKS\\SOLIDWORKS 2026\\samples\\learn\\U-Joint\\bracket.sldprt
to verify dimensional alignment.

Spec summary (docs/getting-started/prefab-ui-u-joint-bracket-runbook.md):
  Outer envelope : 78 mm (X) × 52 mm (Y) × 36 mm (Z depth)
  Inner clearance: 60 mm wide × 34 mm tall  →  9 mm walls on all four sides
  Corner fillets : 9 mm on outer vertical edges of extrusion
  Mounting holes : M4 pilot (4.2 mm dia) at X = ±24 mm on top flange centrelay
  Cable slot     : 16 mm × 8 mm centred on the top flange

This script is generated in the shape the SoC exporter produces.
Checkpoints correspond to save points you would create during an interactive
MCP session.  Run soc_exporter export --session <id> to regenerate from logs.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.config import load_config

# Output directory — sits next to this file
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
        require(await adapter.create_part(name='u_bracket_runbook'), "create_part")

        # ── Sketch 1: frame cross-section ──────────────────────────────────
        # Two concentric rectangles on the Front plane.  SolidWorks extrudes
        # the annular region between outer and inner contour → hollow bracket.
        #
        # Origin at bottom-centre (X=0 at bracket centreline, Y=0 at base).
        # Outer:  X  -39 → +39,  Y   0 → 52   (78 × 52 mm)
        # Inner:  X  -30 → +30,  Y   9 → 43   (60 × 34 mm, 9 mm walls)

        require(await adapter.create_sketch('Front'), "create_sketch")

        require(await adapter.add_rectangle(-39.0, 0.0, 39.0, 52.0), "add_rectangle")
        require(await adapter.add_rectangle(-30.0, 9.0, 30.0, 43.0), "add_rectangle")

        require(await adapter.exit_sketch(), "exit_sketch")

        # ── Extrude 36 mm ──────────────────────────────────────────────────
        require(
            await adapter.create_extrusion(
                ExtrusionParameters(depth=36.0)
            ),
            "create_extrusion",
        )

        # ── Outer vertical-edge fillets (9 mm) ─────────────────────────────
        # Fillet the four long vertical edges of the extrusion.
        # Edge names come from the SolidWorks feature tree; adjust if different.
        require(
            await adapter.add_fillet(
                radius=9.0,
                edge_names=["Edge<1>", "Edge<2>", "Edge<3>", "Edge<4>"],
            ),
            "add_fillet",
        )

        # Checkpoint 1 — base extrude + fillets
        _cp1 = str(_OUT / "u_bracket_runbook_cp1.sldprt")
        require(await adapter.save_file(_cp1), "save_file")

        # -- checkpoint ----------------------------------------------------
        # label:    base-extrude
        # file:     u_bracket_runbook_cp1.sldprt
        # records:  1-6
        # ----------------------------------------------------

        # ── Sketch 2: top-flange mounting features ──────────────────────────
        # The top face of the bracket (Y = 52 mm) has 9 mm of solid material
        # (from Y=43 to Y=52).  Select that face in SolidWorks, then create
        # the sketch.  Coordinates here are in the face-local XZ frame.
        #
        # M4 pilot holes : X = ±24 mm, Z = 18 mm (centred along depth)
        # Cable slot      : 16 mm × 8 mm centred at (X=0, Z=18)

        require(await adapter.create_sketch('Top'), "create_sketch")

        circle_1 = require(await adapter.add_circle(-24.0, 18.0, 2.1), "add_circle")
        circle_2 = require(await adapter.add_circle(24.0, 18.0, 2.1), "add_circle")

        # Cable slot: ±8 mm in X, Z from 14 → 22 (8 mm span around Z=18)
        require(await adapter.add_rectangle(-8.0, 14.0, 8.0, 22.0), "add_rectangle")

        require(await adapter.exit_sketch(), "exit_sketch")

        # Cut through the 9 mm top flange
        require(
            await adapter.create_cut_extrude(ExtrusionParameters(through_all=True)),
            "create_cut_extrude",
        )

        # Checkpoint 2 — mounting features complete
        _cp2 = str(_OUT / "u_bracket_runbook_final.sldprt")
        require(await adapter.save_file(_cp2), "save_file")

        # -- checkpoint ----------------------------------------------------
        # label:    features-added
        # file:     u_bracket_runbook_final.sldprt
        # records:  7-12
        # ----------------------------------------------------

        # ── Verification exports ────────────────────────────────────────────
        # Compare these images against bracket.sldprt AFTER the script runs.
        for view in ("isometric", "front", "top", "right"):
            require(
                await adapter.export_image({
                    "file_path": str(_OUT / f"u_bracket_runbook_{view}.png"),
                    "format_type": "png",
                    "width": 1600,
                    "height": 1000,
                    "view_orientation": view,
                }),
                f"export_image:{view}",
            )

    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    asyncio.run(build_part())
