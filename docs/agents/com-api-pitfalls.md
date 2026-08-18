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

## 11. `GetType()` resolves as a property, not a method, on a freshly-fetched `ActiveDoc`

**Symptom:** `TypeError: 'int' object is not callable` when calling `document.GetType()` —
but the *identical* call on a document just returned by `OpenDoc6`/`NewDocument` works fine.
If this exception is caught by a broad `except Exception: return default` (e.g. this
codebase's `_attempt` helper), the failure is silent: the caller just sees `doc_type == 0`
and takes the wrong branch (e.g. treating an Assembly as unrecognized).

**Root cause:** Late-bound COM dispatch resolves an unknown member name speculatively —
sometimes as a callable method wrapper, sometimes by eagerly invoking it and returning the
*value* (property semantics). Which one you get depends on whether the specific dispatch
object has been flagged for its real interface via `sw_type_info.flag_doc`/`flag_methods`
(`_FlagAsMethod`). A document object returned directly by `OpenDoc6` in this codebase's
adapter is flagged immediately after open. A document re-fetched via `swApp.ActiveDoc` in a
later call (e.g. a resync-before-traversal step) is a **new, unflagged** dispatch wrapping
the same underlying document — `GetType` on it resolves as a property, and calling it with
`()` tries to call the returned `int`.

**Fix:** Never call a zero-arg accessor on a document/feature/component with bare
parentheses unless you know it has just been flagged. Route through the existing
`_get_attr_or_call(obj, "MethodName")` helper, which handles both property and method
resolution:

```python
doc_type = adapter._attempt(
    lambda: int(adapter._get_attr_or_call(document, "GetType") or 0), default=0
)
```

Found and fixed 2026-08-11 while verifying assembly-aware `list_features`
(`_FeatureSelectionService.list_features` in `pywin32_adapter.py`) against a live
SolidWorks session — see `openspec/changes/assembly-aware-list-features/`.

## 12. `IComponent2.GetModelDoc2` raises "Member not found" unless `IComponent2` is flagged first

**Symptom:** `pywintypes.com_error: (-2147352573, 'Member not found.', None, None)` when
calling `component.GetModelDoc2()` on an `IComponent2` object returned by
`IAssemblyDoc.GetComponents`, even though `getattr(component, "GetModelDoc2", None)`
returns something that looks callable.

**Root cause:** Same late-binding ambiguity as #11 and #5, but manifesting as a COM error
instead of a Python `TypeError`: dynamic dispatch returns a speculative callable wrapper for
an attribute name it hasn't resolved a real DISPID for yet, and that wrapper only fails once
actually invoked. `IComponent2` is never flagged anywhere else in the traversal — components
come from `GetComponents`, not from `flag_doc` (which only knows about document-level
interfaces: `IPartDoc`/`IAssemblyDoc`/`IDrawingDoc`).

**Fix:** Flag the component for `IComponent2` before calling any of its methods:

```python
sw_type_info.flag_methods(component, "IComponent2")
resolved_doc = adapter._get_attr_or_call(component, "GetModelDoc2")
```

Found and fixed 2026-08-11 alongside #11, in the same live-verification pass. Before this
fix, every component in a real assembly resolved as `UnresolvedComponent` — the traversal
logic itself was correct (confirmed by unit tests against mock COM fakes), but nothing had
ever exercised it against a real, unflagged `IComponent2` dispatch until then. A reminder
that mock-adapter tests validate the *shape* of a fix, not COM binding behavior itself.

---

## 13. `sw_type_info`'s flag cache can go stale when a dispatch is fetched fresh on every call

**Symptom:** `pywintypes.com_error: (-2147352573, 'Member not found.', None, None)` on a
method that *is* genuinely declared on the interface being flagged — intermittent, and the
specific call site that trips it varies between runs (`sketch_mirror` one run,
`sketch_circular_pattern` the next, both by way of the same helper).

**Root cause:** `sw_type_info._flag_cache` is keyed by `id(obj)` and records which
interfaces have already been flagged for that address. That's safe for dispatches stored in
a long-lived adapter attribute (`adapter.currentModel`, `adapter.swApp`,
`adapter.currentSketchManager`) — the same Python object is reused across calls, so the
cache hit is correct. It is **not** safe for a dispatch obtained via a fresh property fetch
on every call (e.g. `adapter.currentModel.SelectionManager` inside a helper function) —
pywin32 hands back a new Python-side wrapper object each time, even though it wraps the same
underlying COM pointer. Once the old wrapper is garbage-collected, CPython is free to reuse
its address for the next call's wrapper. If that happens, `flag_methods` sees a cache hit for
an object that was never actually flagged, skips `_FlagAsMethod`, and the member resolves
through the ordinary speculative path — which fails for methods needing disambiguation
(`CreateSelectData`, etc.).

**Fix:** For any dispatch fetched fresh on every call (not stored in a persistent adapter
attribute), invalidate its cache entry before flagging so a stale id-collision can never
suppress the real `_FlagAsMethod` call:

```python
sel_mgr = adapter.currentModel.SelectionManager  # fresh wrapper every call
sw_type_info.invalidate_flag_cache(sel_mgr)       # force a real re-flag, ignore any stale hit
sw_type_info.flag_methods(sel_mgr, "ISelectionMgr")
```

**Applies to:** `_select_sketch_entities` in `sketch.py` (shared by `sketch_mirror`,
`sketch_offset`, `sketch_circular_pattern`) — fixed 2026-08-15. Any other call site that
flags a dispatch obtained from a bare property/method access rather than a cached adapter
attribute is at the same risk and should apply the same pre-invalidate.

Separately: `close_model`/`close_all_session_docs` now call
`sw_type_info.invalidate_flag_cache()` (full clear, no args) after closing a document, since
the closed document's own child dispatches (sketch, feature, selection-manager objects) are
about to be freed and could otherwise collide with the *next* document's freshly-opened
dispatches.

---

## Reference: Where to look things up

| Question | Where to look |
|---|---|
| Which class owns a method? | `gen_py/3.13/83A33D31-*x0x34x0.py` — search `def MethodName` and note the class above it |
| Is a name a method or property? | In gen_py class: `def Name(...)` = method; `"Name": (...)` in `_prop_map_get_` = property |
| What DISPID does a method have? | `InvokeTypes(DISPID, ...)` line in the gen_py method body |
| Does a method return IFeature? | Check return type: `(9, 0)` = VT_DISPATCH (object); `(24, 0)` = VT_I4 (integer) |
| Full COM threading rules | See "COM threading architecture" in [CLAUDE.md](../../CLAUDE.md) |
| Runbook for live debugging | See "Troubleshooting Runbook" section in [CLAUDE.md](../../CLAUDE.md) |
