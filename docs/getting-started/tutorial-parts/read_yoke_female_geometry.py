"""Read geometry from SW 2026 sample Yoke_female.sldprt.

Focuses on Sketch12 (bolt holes on top face) since the base body
is known to be identical to yoke_male (Sketch2, Sketch8, Sketch11).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from solidworks_mcp.adapters import create_adapter
from solidworks_mcp.config import load_config

SAMPLE = Path(
    r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\Yoke_female.sldprt"
)


def _dump_sketch(sketch_name: str, adapter: object) -> None:
    raw = adapter
    while raw is not None:
        if hasattr(raw, "currentModel") and hasattr(raw, "_handle_com_operation"):
            break
        raw = getattr(raw, "adapter", None)
    if raw is None or raw.currentModel is None:
        return

    def _op() -> None:
        from solidworks_mcp.adapters import sw_type_info
        model = raw.currentModel
        sw_type_info.flag_doc(model, 1)

        feat = model.FeatureByName(sketch_name)
        if feat is None:
            print(f"  [{sketch_name}] NOT FOUND")
            return

        sw_type_info.flag_methods(feat, "IFeature")
        try:
            sketch = feat.GetSpecificFeature2()
        except Exception as e:
            print(f"  [{sketch_name}] GetSpecificFeature2 failed: {e}")
            return
        if sketch is None:
            print(f"  [{sketch_name}] GetSpecificFeature2 returned None")
            return

        sw_type_info.flag_methods(sketch, "ISketch")
        print(f"\n=== {sketch_name} segments ===")

        segs = None
        try:
            segs = sketch.GetSketchSegments()
        except Exception:
            pass
        if segs is None:
            # Fallback: property access
            try:
                segs = sketch.GetSketchSegments
            except Exception as e:
                print(f"  GetSketchSegments error: {e}")
                return
        if segs is None:
            print("  no segments")
            return

        seg_list = list(segs) if hasattr(segs, "__iter__") else [segs]
        print(f"  count: {len(seg_list)}")
        for seg in seg_list:
            try:
                sw_type_info.flag_methods(seg, "ISketchSegment")
                sw_type_info.flag_methods(seg, "ISketchLine")
                sw_type_info.flag_methods(seg, "ISketchArc")
                try:
                    stype = seg.GetType()
                except Exception:
                    stype = -1
                constr = False
                try:
                    constr = bool(seg.ConstructionGeometry)
                except Exception:
                    pass
                tag = "(construction)" if constr else ""

                # Try to get center/start/end/radius regardless of type
                cp_str, sp_str, ep_str, r_str = "", "", "", ""
                try:
                    cp = seg.GetCenterPoint2()
                    cp_str = f" center=({cp.X*1e3:.4f},{cp.Y*1e3:.4f})"
                except Exception:
                    pass
                try:
                    sp = seg.GetStartPoint2()
                    sp_str = f" start=({sp.X*1e3:.4f},{sp.Y*1e3:.4f})"
                except Exception:
                    pass
                try:
                    ep = seg.GetEndPoint2()
                    ep_str = f" end=({ep.X*1e3:.4f},{ep.Y*1e3:.4f})"
                except Exception:
                    pass
                try:
                    r = seg.GetRadius()
                    r_str = f" r={r*1e3:.4f}"
                except Exception:
                    pass

                print(f"  type={stype} {tag}{cp_str}{r_str}{sp_str}{ep_str} mm")
            except Exception as ex:
                print(f"  seg error: {ex}")

    raw._handle_com_operation(f"dump_{sketch_name}", _op)


async def read() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
        r = await adapter.open_model(str(SAMPLE))
        if not r.is_success:
            print(f"open_model failed: {r.error}")
            return

        # Dump each modeling sketch in the female yoke
        for name in ("Sketch1", "Sketch2", "Sketch8", "Sketch11", "Sketch12"):
            _dump_sketch(name, adapter)

    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    asyncio.run(read())
