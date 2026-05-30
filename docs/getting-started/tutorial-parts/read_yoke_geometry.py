"""Read Yoke_male sketch geometry via COM adapter — follows list_features pattern."""
from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.config import load_config

YOKE_MALE = Path(
    r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\Yoke_male.sldprt"
)


def unwrap_adapter(adapter: Any) -> Any | None:
    """Walk the adapter chain to find the raw PyWin32Adapter (has _attempt)."""
    current: Any | None = adapter
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if hasattr(current, "_attempt") and hasattr(current, "currentModel"):
            return current
        current = getattr(current, "adapter", None)
    return None


def read_geometry(adapter: Any) -> None:
    raw = unwrap_adapter(adapter)
    if raw is None or raw.currentModel is None:
        print("ERROR: no raw adapter or no currentModel")
        return

    model = raw.currentModel

    # --- Bounding box ---
    def get_bbox():
        bodies = model.GetBodies2(0, True)
        if not bodies:
            return None
        return bodies[0].GetBodyBox()

    box = raw._attempt(get_bbox)
    if box:
        print("=== BOUNDING BOX (mm) ===")
        print(f"  X: {box[0]*1000:.3f} to {box[3]*1000:.3f}  W={(box[3]-box[0])*1000:.3f}")
        print(f"  Y: {box[1]*1000:.3f} to {box[4]*1000:.3f}  H={(box[4]-box[1])*1000:.3f}")
        print(f"  Z: {box[2]*1000:.3f} to {box[5]*1000:.3f}  D={(box[5]-box[2])*1000:.3f}")

    # --- Feature tree — mirrors list_features in pywin32_adapter.py ---
    # FirstFeature() and GetNextFeature() are called WITH parens (gen_py early-bound
    # wrappers define them as Python methods).  Each call goes through _attempt so
    # it runs on the COM STA executor thread.
    print("\n=== FEATURE TREE ===")

    feat = raw._attempt(lambda: model.FirstFeature())
    guard = 0
    while feat and guard < 200:
        guard += 1

        name = raw._attempt(lambda f=feat: f.Name, default="?")

        # In gen_py early-bound mode, GetTypeName2 is a property (no parens).
        type_name = raw._attempt(lambda f=feat: f.GetTypeName2, default="?")
        if not isinstance(type_name, str):
            type_name = "?"

        print(f"\n[{name}]  type={type_name}")

        # ---- Sketch plane + segments ----
        if type_name == "ProfileFeature":
            def get_sketch_info(f=feat):
                sketch = f.GetSpecificFeature2
                if sketch is None:
                    return None, []
                # Normal vector identifies the plane: (0,0,1)=Front/XY, (0,1,0)=Top/XZ, (1,0,0)=Right/YZ
                normal = "unknown"
                try:
                    xf = sketch.ModelToSketchTransform
                    ad = xf.ArrayData
                    # SW ModelToSketchTransform ArrayData layout (16 elements):
                    # [r00,r01,r02, r10,r11,r12, r20,r21,r22, tx,ty,tz, scale, 0, 0, 0]
                    # or sometimes [scale, r00..r08, tx,ty,tz]
                    # Normal to sketch in model space = sketch Z-axis (3rd row of rotation)
                    # Try standard layout first (9 rotation + 3 translation)
                    n = len(ad)
                    if n >= 12:
                        nx, ny, nz = round(ad[6],3), round(ad[7],3), round(ad[8],3)
                        # plane_pos = -ad[11]*1000 gives the model-space position
                        # along the plane normal direction (in mm).
                        plane_pos = round(-ad[11]*1000, 3)
                    else:
                        nx, ny, nz, plane_pos = 0, 0, 0, 0
                    if abs(abs(nx)-1) < 0.01:
                        normal = f"Right(YZ) at X={plane_pos}mm"
                    elif abs(abs(ny)-1) < 0.01:
                        normal = f"Top(XZ) at Y={plane_pos}mm"
                    elif abs(abs(nz)-1) < 0.01:
                        normal = f"Front(XY) at Z={plane_pos}mm"
                    else:
                        normal = f"n=({nx},{ny},{nz}) plane_pos={plane_pos}mm"
                except Exception as e:
                    normal = f"xf_err:{e}"
                return normal, sketch.GetSketchSegments or []

            plane_info, segments = raw._attempt(get_sketch_info, default=("unknown", []))
            print(f"  plane={plane_info}")

            for seg in (segments or []):
                def read_seg(s=seg):
                    try:
                        seg_type = s.GetType
                        if seg_type == 0:   # line
                            sp = s.GetStartPoint2
                            ep = s.GetEndPoint2
                            return ("LINE", sp.X*1000, sp.Y*1000, ep.X*1000, ep.Y*1000)
                        elif seg_type == 1:  # arc / circle
                            ctr = s.GetCenterPoint2
                            r = s.GetRadius
                            return ("ARC", ctr.X*1000, ctr.Y*1000, r*1000)
                        return ("OTHER", seg_type)
                    except Exception as e:
                        print(f"  DBG read_seg EXCEPTION: {type(e).__name__}: {e}")
                        return None

                info = raw._attempt(read_seg)
                if info:
                    if info[0] == "LINE":
                        print(f"  LINE  ({info[1]:.3f},{info[2]:.3f}) -> ({info[3]:.3f},{info[4]:.3f})")
                    elif info[0] == "ARC":
                        print(f"  CIRCLE  ctr=({info[1]:.3f},{info[2]:.3f})  r={info[3]:.3f}  dia={info[3]*2:.3f}")
                    elif info[0] == "OTHER":
                        print(f"  OTHER type={info[1]}")

        # ---- Extrude depth ----
        # SW requires AccessSelections2(model) before reading definition properties.
        if type_name in ("Boss", "Cut", "Extrusion"):
            def read_depth(f=feat, m=model):
                defn = None
                try:
                    defn = f.GetDefinition()
                except Exception:
                    defn = f.GetDefinition
                if defn is None:
                    return {}
                try:
                    defn.AccessSelections2(m, None)
                except Exception:
                    pass
                results = {}
                for attr in ("Depth", "Depth2", "EndCondition", "EndCondition2"):
                    try:
                        v = getattr(defn, attr)
                        if attr.startswith("Depth"):
                            results[attr] = round(v * 1000, 4)
                        else:
                            results[attr] = v
                    except Exception:
                        pass
                try:
                    defn.ReleaseSelectionAccess()
                except Exception:
                    pass
                return results

            depth_info = raw._attempt(read_depth)
            if depth_info:
                for k, v in depth_info.items():
                    print(f"  {k} = {v}")

        # GetNextFeature is a property in gen_py early-bound mode (no parens).
        feat = raw._attempt(lambda f=feat: f.GetNextFeature)


async def main() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
        result = await adapter.open_model(str(YOKE_MALE))
        if not result.is_success:
            print(f"open_model failed: {result.error}")
            return
        read_geometry(adapter)
    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
