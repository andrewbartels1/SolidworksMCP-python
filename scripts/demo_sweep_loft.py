r"""Live end-to-end demo for the Phase 1 sweep and loft operations.

Builds a single multibody part that exercises both methods delivered under
fork issue #2 / upstream issue #4:

    create_loft, create_sweep

Layout (mm):

* **Lofted cone** centred at X=+90: a 30 mm-radius circle on the Front plane
  lofted to a 12 mm-radius circle on a reference plane offset 80 mm in front
  of it — a cone/gear-like tapered bevel (``create_loft``).
* **Swept coil spring** centred near the origin: a 3.5 mm-radius circular
  profile on the Front plane swept along a helix built from an 18 mm-radius
  base circle on the Top plane (60 mm tall, 12 mm pitch) (``create_sweep``).

Geometry the Phase 1 surface does not yet build natively — an offset
reference plane for the loft's second profile, and a helix for the sweep
path — is created with raw COM (InsertRefPlane / InsertHelix), exactly as a
caller would until Phase 3 reference-geometry support lands.

On success the script saves the part and two PNG screenshots (isometric and
trimetric) to ``out/`` and exits 0.  Run with the project virtualenv on a
Windows box that already has SolidWorks open::

    .\.venv\Scripts\python.exe scripts\demo_sweep_loft.py
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from solidworks_mcp.adapters.base import (  # noqa: E402
    LoftParameters,
    SweepParameters,
)
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter  # noqa: E402


def _check(label: str, result) -> None:
    """Raise with the COM error attached when an adapter result is not success."""
    if not result.is_success:
        raise RuntimeError(f"{label} failed: {result.error}")
    print(f"  OK  {label}")


def _read_member(obj, name):
    """Read a COM accessor that pywin32 may expose as a method or a property.

    Calls the member when it is callable and falls back to the raw member if
    the call raises, so it yields the value whether the dispatch is flagged,
    unflagged, or a property that returns a COM object.
    """
    member = getattr(obj, name, None)
    if not callable(member):
        return member
    try:
        return member()
    except Exception:
        return member


def _feature_name_by_type(adapter, type_name: str) -> str:
    """Return the name of the last feature whose GetTypeName2 matches.

    Used to recover a feature whose creator call returns None on success
    (e.g. InsertHelix), by walking the feature tree with method flagging.
    """
    from solidworks_mcp.adapters import sw_type_info

    def _flag(obj, iface):
        try:
            sw_type_info.flag_methods(obj, iface)
        except Exception:
            pass

    _flag(adapter.currentModel, "IModelDoc2")
    found = ""
    feat = _read_member(adapter.currentModel, "FirstFeature")
    for _ in range(5000):
        if not feat:
            break
        _flag(feat, "IFeature")
        try:
            if _read_member(feat, "GetTypeName2") == type_name:
                found = str(_read_member(feat, "Name"))
        except Exception:
            pass
        feat = _read_member(feat, "GetNextFeature")
    return found


async def build_demo_part(out_dir: Path) -> dict[str, str]:
    """Build the demo part end-to-end and return artefact paths."""
    out_dir.mkdir(parents=True, exist_ok=True)

    adapter = PyWin32Adapter({})
    print("Connecting to SolidWorks ...")
    await adapter.connect()
    print(f"Connected: swApp={type(adapter.swApp).__name__}")

    try:
        part = await adapter.create_part()
        _check("create_part", part)
        print(f"  doc: {part.data.name}")

        # ------------------------------------------------------------------
        # Feature 1: lofted cone (tapered bevel) centred at X=+90.
        # ------------------------------------------------------------------
        s_loft1 = await adapter.create_sketch("Front")
        _check("create_sketch Front (loft profile 1)", s_loft1)
        _check("add_circle R30 (loft base)", await adapter.add_circle(90.0, 0.0, 30.0))
        _check("exit_sketch (loft profile 1)", await adapter.exit_sketch())

        # Reference plane 80 mm in front of the Front plane (FirstConstraint
        # flag 8 == distance; InsertRefPlane works in metres).
        front = adapter.currentModel.FeatureByName("Front Plane")
        if not (front and front.Select2(False, 0)):
            raise RuntimeError("could not select Front plane for the offset plane")
        ref_plane = adapter.currentModel.FeatureManager.InsertRefPlane(
            8, 0.080, 0, 0, 0, 0
        )
        adapter.currentModel.ClearSelection2(True)
        plane_name = str(ref_plane.Name) if ref_plane else ""
        if not plane_name:
            raise RuntimeError("InsertRefPlane returned no reference plane")
        print(f"  OK  InsertRefPlane -> {plane_name}")

        s_loft2 = await adapter.create_sketch(plane_name)
        _check("create_sketch offset plane (loft profile 2)", s_loft2)
        _check("add_circle R12 (loft top)", await adapter.add_circle(90.0, 0.0, 12.0))
        _check("exit_sketch (loft profile 2)", await adapter.exit_sketch())

        _check(
            "create_loft (R30 -> R12 tapered cone)",
            await adapter.create_loft(
                LoftParameters(profiles=[s_loft1.data, s_loft2.data])
            ),
        )

        # ------------------------------------------------------------------
        # Feature 2: swept coil spring centred at the origin.
        # ------------------------------------------------------------------
        base = await adapter.create_sketch("Top")
        _check("create_sketch Top (helix base)", base)
        _check("add_circle R18 (helix base)", await adapter.add_circle(0.0, 0.0, 18.0))

        # InsertHelix consumes the *open* base sketch directly; it lives on
        # IModelDoc2 and returns None on success, so read the name back from
        # the tree. Height & pitch (swHelixDefinedBy_e == 2): 60 mm tall,
        # 12 mm pitch -> 5 revolutions.
        adapter.currentModel.InsertHelix(
            False, True, False, False, 2, 0.060, 0.012, 0.0, 0.0, 0.0
        )
        adapter.currentModel.ClearSelection2(True)
        helix_name = _feature_name_by_type(adapter, "Helix")
        if not helix_name:
            raise RuntimeError("InsertHelix did not create a helix feature")
        print(f"  OK  InsertHelix -> {helix_name}")

        prof = await adapter.create_sketch("Front")
        _check("create_sketch Front (sweep profile)", prof)
        _check(
            "add_circle R3.5 (sweep profile at helix start)",
            await adapter.add_circle(18.0, 0.0, 3.5),
        )
        _check("exit_sketch (sweep profile)", await adapter.exit_sketch())

        _check(
            "create_sweep (circular profile along helix -> spring)",
            await adapter.create_sweep(SweepParameters(path=helix_name)),
        )

        # ------------------------------------------------------------------
        # Persist + screenshots.
        # ------------------------------------------------------------------
        part_path = (out_dir / "sweep_loft_demo.SLDPRT").resolve()
        _check(f"save_file -> {part_path}", await adapter.save_file(str(part_path)))

        shots: dict[str, str] = {}
        for orientation in ("isometric", "trimetric"):
            img_path = (out_dir / f"sweep_loft_demo_{orientation}.png").resolve()
            _check(
                f"export_image ({orientation}) -> {img_path}",
                await adapter.export_image(
                    {
                        "file_path": str(img_path),
                        "format_type": "png",
                        "width": 1600,
                        "height": 1000,
                        "view_orientation": orientation,
                    }
                ),
            )
            shots[f"screenshot_{orientation}"] = str(img_path)

        return {"part": str(part_path), **shots}
    finally:
        try:
            await adapter.close_model(save=False)
        except Exception:  # noqa: BLE001
            pass
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
