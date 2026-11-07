r"""Build the arched monitor stand through the MCP tools.

This replays the tool calls an agent made from the prompt on the Demos page
(``docs/demos.md#monitor-stand``), with every dimension a command-line
option, so the stand can be rebuilt at a new size in one run.

The defaults are the stand as finished by hand after that session: 66 mm
tall with a 26 mm top, so the legs stay 40 mm, and an 11.46 mm pocket that
leaves a 14.54 mm floor under the monitor. The session built it 55 mm tall
with a 3 mm pocket (``--height 55 --top 15 --pocket-depth 3``).

The one difference from the hand-finished part: there, the pocket's plane
sits on the top face, so it follows the height if the height is edited in
SolidWorks. The tools can only offset a plane from a named plane, so here
it is Top Plane offset by the height. The solid is the same; to change the
height, rerun the script rather than editing the extrusion by hand.

The stand is a top plate on four square legs. The openings at the front,
left and right are arched (large fillets where the legs meet the top); the
back opening stays square, for cables. A shallow pocket in the top, a
little larger than the monitor's base, holds the monitor in place.

Build sequence (SolidWorks axes: X wide, Y up, Z deep, front = +Z)
-------------------------------------------------------------------
1. ``create_part``, ``set_units`` mm.
2. Top Plane: a W x D rectangle about the origin, extruded H up: a block.
3. Front Plane: the front/back opening, cut through both ways.
4. Right Plane: the left/right opening, cut through both ways. Four legs
   remain under the top.
5. One ``add_fillet`` on the six edges where a leg's inner face meets the
   underside, picked by each edge's midpoint (metres): two for the front
   arch, four for the side arches. The back legs' edges facing the back
   opening are left sharp.
6. The pocket: ``create_reference_plane`` on the top face (Top Plane
   offset by the height), a rectangle the base's size plus the clearance
   on each side, and a blind cut down into the top.
7. ``rebuild_model``, then ``verify_model`` against a hand calculation.
8. ``save_part`` and, with ``--stl``, ``export_stl``.

Every sketch is symmetric about the origin, so the Top and Right planes'
sketch axes (which run along -Z) cannot mirror anything.

Run on Windows with SolidWorks open, from the repository root::

    .\.venv\Scripts\python.exe scripts\demo_monitor_stand.py --out "C:\path\to\MonitorStand.SLDPRT"

Change a dimension and rebuild over the saved part::

    .\.venv\Scripts\python.exe scripts\demo_monitor_stand.py --out "C:\path\to\MonitorStand.SLDPRT" --height 70 --fillet 30 --pocket-depth 8 --replace --stl

``--replace`` closes the part if it is open in SolidWorks (unsaved changes
to it are lost) and overwrites the file. ``--mock`` runs every call against
the mock adapter instead, without SolidWorks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


@dataclass(frozen=True)
class Stand:
    """The stand's dimensions, all in mm."""

    base_width: float = 173.71  # the monitor base, along X
    base_depth: float = 170.0  # the monitor base, along Z
    margin: float = 10.0  # added on every side of the monitor base
    top: float = 26.0  # top plate thickness
    height: float = 66.0  # floor to top face
    leg: float = 40.0  # square leg size
    fillet: float = 25.0  # arch fillet radius
    pocket_clearance: float = 1.0  # pocket larger than the base, each side
    pocket_depth: float = 11.46  # how far the monitor sits into the top

    @property
    def pocket_width(self) -> float:
        """Pocket size along X."""
        return self.base_width + 2 * self.pocket_clearance

    @property
    def pocket_length(self) -> float:
        """Pocket size along Z."""
        return self.base_depth + 2 * self.pocket_clearance

    @property
    def width(self) -> float:
        """Overall width along X."""
        return self.base_width + 2 * self.margin

    @property
    def depth(self) -> float:
        """Overall depth along Z."""
        return self.base_depth + 2 * self.margin

    @property
    def leg_height(self) -> float:
        """Height of the legs, floor to the underside of the top."""
        return self.height - self.top

    def problems(self) -> list[str]:
        """What makes these dimensions unbuildable; empty when they are fine."""
        found = []
        if min(self.width, self.depth, self.top, self.height, self.leg) <= 0:
            found.append("every size must be positive")
        if self.leg_height <= 0:
            found.append(f"height {self.height:g} must exceed top {self.top:g}")
        if 2 * self.leg >= min(self.width, self.depth):
            found.append(f"two {self.leg:g} mm legs do not fit across the stand")
        if self.fillet <= 0 or self.fillet >= self.leg_height:
            found.append(
                f"fillet {self.fillet:g} must be above 0 and below the "
                f"{self.leg_height:g} mm leg height"
            )
        opening = min(self.width, self.depth) - 2 * self.leg
        if 2 * self.fillet >= opening:
            found.append(
                f"two {self.fillet:g} mm fillets do not fit in the "
                f"{opening:g} mm opening"
            )
        if self.pocket_clearance < 0:
            found.append("pocket clearance cannot be negative")
        if self.pocket_width >= self.width or self.pocket_length >= self.depth:
            found.append("the pocket leaves no rim: lower the clearance or raise the margin")
        if self.pocket_depth <= 0 or self.pocket_depth >= self.top:
            found.append(
                f"pocket depth {self.pocket_depth:g} must be above 0 and below "
                f"the {self.top:g} mm top"
            )
        return found

    def expected_volume_mm3(self) -> float:
        """Top plate plus four legs plus six fillets, less the pocket.

        Leaves out the small blend where the front and side arches meet at
        each front leg's inner corner, so it reads about 0.3 % low for the
        default stand; the check allows 1 %.
        """
        plate = self.width * self.depth * self.top
        legs = 4 * self.leg**2 * self.leg_height
        fillets = 6 * (1 - math.pi / 4) * self.fillet**2 * self.leg
        pocket = self.pocket_width * self.pocket_length * self.pocket_depth
        return plate + legs + fillets - pocket

    def arch_edges_m(self) -> list[str]:
        """Midpoints of the six arch edges, as 'x,y,z' in metres."""
        y = self.leg_height
        front_x = self.width / 2 - self.leg  # a front leg's inner X face
        front_z = self.depth / 2 - self.leg / 2  # along that leg's depth
        side_x = self.width / 2 - self.leg / 2  # along a leg's width
        side_z = self.depth / 2 - self.leg  # a leg's inner Z face
        points = [
            (front_x, y, front_z),  # front arch, right leg
            (-front_x, y, front_z),  # front arch, left leg
            (side_x, y, side_z),  # right arch, front leg
            (-side_x, y, side_z),  # left arch, front leg
            (side_x, y, -side_z),  # right arch, back leg
            (-side_x, y, -side_z),  # left arch, back leg
        ]
        return [",".join(f"{v / 1000:.6f}" for v in p) for p in points]


class Session:
    """Calls registered MCP tools by name, prints each, and keeps a transcript."""

    def __init__(self, tools: dict[str, Any]) -> None:
        self.tools = tools
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, name: str, args: dict[str, Any] | None = None) -> dict:
        """Call one tool and require success."""
        shown = json.dumps(args or {}, ensure_ascii=False)
        print(f"{len(self.calls) + 1:>2}. {name}({shown})")
        result = await (self.tools[name]() if args is None else self.tools[name](args))
        self.calls.append({"tool": name, "args": args or {}})
        if result.get("status") != "success":
            raise RuntimeError(f"{name} failed: {result.get('message')}")
        print(f"    -> {result.get('message')}")
        return result


async def _tools(adapter: Any) -> dict[str, Any]:
    """Register the tool families the build uses; name -> tool function."""
    from fastmcp import FastMCP

    from solidworks_mcp.tools.analysis import register_analysis_tools
    from solidworks_mcp.tools.export import register_export_tools
    from solidworks_mcp.tools.file_management import register_file_management_tools
    from solidworks_mcp.tools.modeling import register_modeling_tools
    from solidworks_mcp.tools.sketching import register_sketching_tools

    mcp = FastMCP("monitor-stand-demo")
    for register in (
        register_modeling_tools,
        register_sketching_tools,
        register_analysis_tools,
        register_file_management_tools,
        register_export_tools,
    ):
        await register(mcp, adapter, {})
    return {t.name: t.fn for t in await mcp.list_tools()}


async def _close_if_open(call: Session, out: Path) -> None:
    """Close the saved stand without saving, if SolidWorks has it open."""
    listed = await call("list_open_documents")
    for doc in listed.get("documents", []):
        if Path(doc.get("path") or "").resolve() == out.resolve():
            await call("activate_document", {"title_or_path": str(out)})
            await call("close_model", {"save": False})


def _mm(value: float) -> float:
    """Round a length to 0.0001 mm so the calls read cleanly."""
    return round(value, 4)


async def _centred_rectangle(call: Session, plane: str, width: float, length: float) -> None:
    """Sketch a rectangle centred on the origin of ``plane`` and exit the sketch."""
    await call("create_sketch", {"plane": plane})
    await call(
        "add_rectangle",
        {"x1": -_mm(width / 2), "y1": -_mm(length / 2), "x2": _mm(width / 2), "y2": _mm(length / 2)},
    )
    await call("exit_sketch")


async def build(stand: Stand, out: Path, replace: bool, stl: bool, call: Session) -> None:
    """Run the build's tool calls in order."""
    if replace:
        await _close_if_open(call, out)

    await call("create_part", {"name": out.stem, "units": "mm"})
    await call("set_units", {"unit_system": "mm"})

    # Block: the full footprint, extruded to the full height.
    await _centred_rectangle(call, "Top", stand.width, stand.depth)
    await call("create_extrusion", {"sketch_name": "Sketch1", "depth": stand.height})

    # Front/back opening, between the legs along X.
    inner_x = _mm(stand.width / 2 - stand.leg)
    await call("create_sketch", {"plane": "Front"})
    await call(
        "add_rectangle",
        {"x1": -inner_x, "y1": 0, "x2": inner_x, "y2": _mm(stand.leg_height)},
    )
    await call("exit_sketch")
    cut_depth = math.ceil(max(stand.width, stand.depth) + 10)
    await call(
        "create_cut_extrude",
        {"sketch_name": "Sketch2", "depth": cut_depth, "end_condition": "ThroughAllBoth"},
    )

    # Left/right opening, between the legs along Z.
    inner_z = _mm(stand.depth / 2 - stand.leg)
    await call("create_sketch", {"plane": "Right"})
    await call(
        "add_rectangle",
        {"x1": -inner_z, "y1": 0, "x2": inner_z, "y2": _mm(stand.leg_height)},
    )
    await call("exit_sketch")
    await call(
        "create_cut_extrude",
        {"sketch_name": "Sketch3", "depth": cut_depth, "end_condition": "ThroughAllBoth"},
    )

    # Arches: front, left and right. The back stays square.
    await call("add_fillet", {"radius": stand.fillet, "edge_names": stand.arch_edges_m()})

    # Pocket: a plane on the top face, the base's outline plus clearance,
    # cut down into the top. The cut finds the material itself.
    plane = await call("create_reference_plane", {"reference": "Top Plane", "offset": stand.height})
    await _centred_rectangle(call, plane["plane"]["name"], stand.pocket_width, stand.pocket_length)
    await call(
        "create_cut_extrude",
        {"sketch_name": "Sketch4", "depth": stand.pocket_depth, "end_condition": "Blind"},
    )

    await call("rebuild_model")
    verdict = await call(
        "verify_model",
        {
            "bounding_box_mm": [_mm(stand.width), _mm(stand.height), _mm(stand.depth)],
            "volume_mm3": round(stand.expected_volume_mm3(), 1),
            "solid_body_count": 1,
            "feature_count": 6,  # extrude, two cuts, fillet, plane, pocket
            "relative_tolerance": 0.01,
        },
    )
    if verdict.get("verdict") != "pass":
        failed = [c["name"] for c in verdict.get("checks", []) if c.get("passed") is not True]
        raise RuntimeError(f"verify_model did not pass: {failed}")

    await call("save_part", {"file_path": str(out), "overwrite": replace})
    if stl:
        await call(
            "export_stl",
            {"file_path": str(out.with_suffix(".stl")), "format_type": "stl"},
        )


def _parse(argv: list[str] | None) -> argparse.Namespace:
    d = Stand()
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--out", type=Path, required=True, help="where to save the .SLDPRT")
    p.add_argument("--base-width", type=float, default=d.base_width, help="monitor base width, X (mm)")
    p.add_argument("--base-depth", type=float, default=d.base_depth, help="monitor base depth, Z (mm)")
    p.add_argument("--margin", type=float, default=d.margin, help="added on each side (mm)")
    p.add_argument("--top", type=float, default=d.top, help="top plate thickness (mm)")
    p.add_argument("--height", type=float, default=d.height, help="overall height (mm)")
    p.add_argument("--leg", type=float, default=d.leg, help="square leg size (mm)")
    p.add_argument("--fillet", type=float, default=d.fillet, help="arch fillet radius (mm)")
    p.add_argument(
        "--pocket-clearance", type=float, default=d.pocket_clearance,
        help="pocket larger than the base on each side (mm)",
    )
    p.add_argument("--pocket-depth", type=float, default=d.pocket_depth, help="pocket depth (mm)")
    p.add_argument("--replace", action="store_true", help="close the open part and overwrite the file")
    p.add_argument("--stl", action="store_true", help="also export an STL beside the part")
    p.add_argument("--calls-json", type=Path, help="write the tool calls made to this file")
    p.add_argument("--mock", action="store_true", help="use the mock adapter, not SolidWorks")
    return p.parse_args(argv)


async def _run(args: argparse.Namespace, stand: Stand) -> list[dict[str, Any]]:
    if args.mock:
        from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter

        adapter: Any = MockSolidWorksAdapter({})
    else:
        from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

        adapter = PyWin32Adapter({})
    await adapter.connect()
    try:
        call = Session(await _tools(adapter))
        await build(stand, args.out, args.replace, args.stl, call)
        return call.calls
    finally:
        await adapter.disconnect()


def main(argv: list[str] | None = None) -> int:
    """Parse options, build the stand, and report what was made."""
    args = _parse(argv)
    stand = Stand(
        base_width=args.base_width,
        base_depth=args.base_depth,
        margin=args.margin,
        top=args.top,
        height=args.height,
        leg=args.leg,
        fillet=args.fillet,
        pocket_clearance=args.pocket_clearance,
        pocket_depth=args.pocket_depth,
    )
    if problems := stand.problems():
        print("Can't build this stand:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    if args.out.suffix.upper() != ".SLDPRT":
        print("--out must end in .SLDPRT", file=sys.stderr)
        return 2
    if args.out.exists() and not args.replace:
        print(f"{args.out} exists; pass --replace to rebuild over it", file=sys.stderr)
        return 2

    print(
        f"Stand {stand.width:g} x {stand.depth:g} x {stand.height:g} mm, "
        f"{stand.top:g} mm top, {stand.leg:g} mm legs, R{stand.fillet:g} arches, "
        f"{stand.pocket_width:g} x {stand.pocket_length:g} x {stand.pocket_depth:g} mm pocket"
    )
    try:
        calls = asyncio.run(_run(args, stand))
    except RuntimeError as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1
    if args.calls_json:
        args.calls_json.write_text(json.dumps(calls, indent=2), encoding="utf-8")
    print(f"\nDone: {len(calls)} tool calls. Saved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
