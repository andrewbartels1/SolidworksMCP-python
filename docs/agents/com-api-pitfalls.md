# COM API Pitfalls for LLM Agents

This page documents hard-won lessons from debugging the SolidWorks COM bridge.
If you are an AI coding assistant (Claude, GPT-4, Gemini, Copilot, etc.) working on this codebase,
**read this page before touching any COM-related code**.
Every entry below caused a real runtime failure that required hours to diagnose.

!!! tip "For LLM agents"
    The patterns here are not obvious from the SolidWorks API docs alone.
    They are the delta between "what the documentation says" and "what actually works"
    under pywin32 late-binding on SW 2025/2026.

---

## 1. `SelectByID2` — `Callout` must be `VT_DISPATCH` null, not `None`

**Symptom:** `(-2147352571, 'Type mismatch.', None, 8)` when calling `SelectByID2`.

**Root cause:** The `Callout` parameter (8th argument, type `VT_DISPATCH`) expects a COM
null pointer, not a Python `None`. Python `None` marshals as `VT_NULL` which SolidWorks
rejects with `DISP_E_TYPEMISMATCH`.

**Fix:**

```python
import pythoncom
import win32com.client as _win32com

null_callout = _win32com.VARIANT(pythoncom.VT_DISPATCH, None)
model.Extension.SelectByID2(
    "", "EDGE", x, y, z,
    append, mark,
    null_callout,   # <- NOT plain None
    0,
)
```

**Applies to:** Every call to `SelectByID2` or `SelectByID` that doesn't need a real callout object.
The same issue occurs for `FACE`, `EDGE`, `VERTEX`, and other entity types.

---

## 2. `InsertFeatureChamfer` lives on `IFeatureManager`, not `IModelDocExtension`

**Symptom:** `<unknown>.InsertFeatureChamfer` error when calling through `model.Extension`.

**Root cause:** `InsertFeatureChamfer` (DISPID 83) is a method of `IFeatureManager`, not
`IModelDocExtension`. Routing it through `model.Extension` causes `DISP_E_MEMBERNOTFOUND`.

**Fix:**

```python
import math

fm = model.FeatureManager          # IFeatureManager (property access, no parens)
feature = fm.InsertFeatureChamfer(
    1,                             # Options
    1,                             # ChamferType = swChamferEqualDistance
    distance_m,                    # Width in metres
    math.pi / 4,                   # Angle (45 degrees)
    0.0,                           # OtherDist (unused for equal-distance)
    0.0, 0.0, 0.0,                 # VertexChamDist1, 2, 3 (unused)
)
```

**Applies to:** Any chamfer feature creation. Do not use `model.Extension.InsertFeatureChamfer`.

---

## 3. `ForceRebuild3` must run before coordinate-based edge/face selection

**Symptom:** `SelectByID2("", "EDGE", x, y, z, ...)` returns `False` even when the coordinate
is geometrically on an edge.

**Root cause:** After creating a feature (revolve, cut, extrude), the new edges are not
tessellated until the model is explicitly rebuilt. `SelectByID2` uses the tessellated mesh to
find nearby entities; without it, the edge does not exist in the selection index.

**Fix:** Call `ForceRebuild3(True)` before the first coordinate-based selection in any
feature operation:

```python
model.ForceRebuild3(True)   # True = top-level only (faster); False = deep rebuild
model.Extension.SelectByID2("", "EDGE", x, y, z, False, 0, null_callout, 0)
```

**Only needed once** per feature-creation sequence, before the first `SelectByID2` call.

---

## 4. `GetTessellation` is on `IFace2`, not on `IEdge`

**Symptom:** `<source>.GetTessellation` error when iterating `body.GetEdges()` and calling
`edge.GetTessellation(tol)`.

**Root cause:** `GetTessellation` is a method of `IFace2` (face objects), not `IEdge`.
Edge objects do not have a tessellation method accessible via late binding.

**What to use instead for edge sampling:** `IEdge.GetCurveParams2` (property, no parens) returns
`[t0, t1, ...]`; then use the `ICurve` returned by `IEdge.GetCurve` and call
`curve.Evaluate2(t, 0)` to sample points.

```python
params = edge.GetCurveParams2    # property — no ()
curve  = edge.GetCurve           # property — no ()
t0, t1 = float(params[0]), float(params[1])
pt = curve.Evaluate2((t0 + t1) / 2, 0)   # midpoint
```

But prefer `SelectByID2` with coordinates over body traversal — it is faster and more reliable.

---

## 5. Zero-arg COM methods accessed without `()` in late binding

**Symptom:** `TypeError: 'str' object is not callable` or `TypeError: 'tuple' object is not callable`.

**Root cause:** Under pywin32 late binding, zero-argument COM methods are returned as their
result value (property-style), not as callable objects. Calling `()` on the result tries to
invoke the returned value (a string, tuple, etc.) as a function.

**Examples:**

```python
# WRONG
title = model.GetTitle()     # TypeError: 'str' is not callable
params = edge.GetCurveParams2()  # TypeError: 'tuple' is not callable

# CORRECT
title = model.GetTitle       # returns the string directly
params = edge.GetCurveParams2    # returns the tuple directly
```

**Rule:** Any SW method with no parameters must be accessed **without** `()`.
The `sw_type_info.flag_methods` system handles which names are treated as methods vs properties.
Check `gen_py` (`IEdge`, `IModelDoc2`, etc.) to see whether a name is a `def` (method) or
in `_prop_map_get_` (property).

---

## 6. `FeatureChamfer(Width, Angle, Flip)` returns `int`, not `IFeature`

**Symptom:** Checking `if not feature:` fails even on success; `feature.Name` crashes.

**Root cause:** `IModelDoc2.FeatureChamfer(Width, Angle, Flip)` (DISPID 65583) returns
`VT_I4` (an integer): `1` on success, `0` on failure. It does **not** return an `IFeature`.
Code that treats the return value as a COM object will fail.

**Fix:** Use `IFeatureManager.InsertFeatureChamfer` (see pitfall #2) which returns a proper
`IFeature`. If you must use the `IModelDoc2` variant as a fallback, check the int:

```python
result_int = model.FeatureChamfer(width_m, math.pi / 4, False)
if not result_int:
    raise Exception("FeatureChamfer returned 0 (failure)")
# result_int is now 1 (truthy), not an IFeature
```

---

## 7. `IModelDoc2.FeatureFillet3` on SW 2025+ returns `int`, not `IFeature`

**Symptom:** `feature.Name` raises `AttributeError: int object has no attribute Name`.

**Root cause:** Starting with SW 2025 (major version ≥ 33), `IModelDoc2.FeatureFillet3`
returns `VT_I4` (1 = success, 0 = failure), not an `IFeature` dispatch object.
The older `IFeatureManager.FeatureFillet3` still returns `IFeature` on older builds.

**Fix:** Branch on SW major version:

```python
rev = adapter.swApp.RevisionNumber
major = int(str(rev).split(".")[0])

if major >= 33:
    result_code = model.FeatureFillet3(radius_m, True, 0, False, 0, 0, None, False, False)
    if not result_code:
        raise Exception("FeatureFillet3 returned 0")
    # Feature exists but IFeature reference is not available; name defaults to "Fillet"
else:
    feature = model.FeatureManager.FeatureFillet3(radius_m, 0, 0, 0, 0, ...)
    if not feature:
        raise Exception("FeatureFillet3 returned None")
    name = feature.Name
```

---

## 8. The `<unknown>.<Method>` error pattern

**Symptom:** Error message like `<unknown>.InsertFeatureChamfer` or `GetEdges.GetTessellation`.

**Root cause:** This is pywin32's error format when `IDispatch.GetIdsOfNames` returns
`DISP_E_MEMBERNOTFOUND` for a method name. It means you are calling a method on the **wrong COM
interface** — the COM object does not know that method name.

**The format:** `<ProgId>.<MethodName>` where `<ProgId>` is how pywin32 identified the object
(`<unknown>` if it has no registered ProgId, or a method name if the object was returned from a call).

**How to diagnose:**
1. Check the gen_py file for which class owns the method (search for `def MethodName`).
2. Confirm the class name printed near the `def` is the interface you are calling through.
3. If they differ, navigate through the correct property chain to reach the right interface.

---

## 9. `InsertRefPlane` for face sketches is more reliable than `SelectByID2 FACE`

**Symptom:** Sketch placed via `SelectByID2 FACE` fails after a parametric cut operation
because the face topology name has changed and the new face isn't found.

**Fix:** Create an offset reference plane from a named plane (e.g. Top Plane) and open a
sketch on that instead:

```python
top_plane = model.FeatureByName("Top Plane") or model.FeatureByName("Planta")
top_plane.Select2(False, 0)
# swRefPlaneReferenceConstraints_Distance = 8
offset_feat = model.FeatureManager.InsertRefPlane(8, offset_m, 0, 0.0, 0, 0.0)
offset_feat.Select2(False, 0)
sketch = model.SketchManager.InsertSketch(True)
```

See [`build_yoke_female_artifact.py`](../getting-started/tutorial-parts/build_yoke_female_artifact.py)
for a full working implementation.

---

## 10. `ThroughAll` vs `ThroughAllBoth` for mid-plane sketches

**Symptom:** A cut extruded from a mid-plane sketch (e.g. Top plane at Y=0) only cuts
in one direction, leaving half the material untouched.

**Root cause:** `swEndCondThroughAll` (value `1`) cuts only in Direction 1 from the sketch
plane. When the sketch is at Y=0 and the body extends from Y=-10 to Y=+10, Direction 1 goes
to Y=+10 but Direction 2 is not cut.

**Fix:** Use `swEndCondThroughAllBoth` (value `9`) or pass `both_directions=True`:

```python
await adapter.create_cut_extrude(
    ExtrusionParameters(end_condition="ThroughAllBoth")
)
```

---

## Reference: Where to look things up

| Question | Where to look |
|---|---|
| Which class owns a method? | `gen_py/3.11/83A33D31-*x0x34x0.py` — search `def MethodName` and note the class above it |
| Is a name a method or property? | In gen_py class: `def Name(...)` = method; `"Name": (...)` in `_prop_map_get_` = property |
| What DISPID does a method have? | `InvokeTypes(DISPID, ...)` line in the gen_py method body |
| Does a method return IFeature? | Check return type: `(9, 0)` = VT_DISPATCH (object); `(24, 0)` = VT_I4 (integer) |
| Full COM threading rules | See "COM threading architecture" in [CLAUDE.md](../../CLAUDE.md) |
| Runbook for live debugging | See "Troubleshooting Runbook" section in [CLAUDE.md](../../CLAUDE.md) |
