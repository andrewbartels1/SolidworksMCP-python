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

## 13. `ToolsCheckInterference2` cannot report a result under late binding

**Symptom:** the call either raises, or succeeds while telling you nothing — both
out-parameters come back `None` on an assembly that visibly interferes.

**Root cause:** `IAssemblyDoc::ToolsCheckInterference2` is declared `Sub` — it returns
nothing — and reports through two `ByRef` out-parameters, `PComp` and `PFace`. Under
pywin32 late binding there is no call form that populates them. Every variant, measured
against a two-component assembly built from the same part twice:

| Call form | Result |
|---|---|
| `pythoncom.Missing` for both out-params | `TypeError: Objects of type 'PyOleMissing' can not be converted to a COM VARIANT` |
| three arguments, out-params omitted | `com_error: (-2147352561, 'Parameter not optional.', None, None)` |
| plain Python `None` for both | `com_error: (-2147352571, 'Type mismatch.', None, 4)` |
| `VARIANT(VT_BYREF \| VT_ARRAY \| VT_DISPATCH, None)` | `com_error: (-2147352571, 'Type mismatch.', None, 4)` |
| component array as `LpComponents` | `com_error: (-2147417851, 'The server threw an exception.', None, None)` |
| `VARIANT(VT_BYREF \| VT_VARIANT, None)` for both | **accepted** — returns `None`, and `PComp.value` / `PFace.value` are both `None`, for an interfering *and* a non-interfering assembly alike |

The last row is the dangerous one: nothing raises, so it reads as a clean result.

**The mistake this invites:** treating the return value as a count.

```python
# WRONG — ToolsCheckInterference2 is a Sub; there is no return value to read.
raw = model.ToolsCheckInterference2(0, None, coincident, missing, missing)
count = int(raw[0]) if raw else 0     # -> 0, i.e. "no interference", always
```

An inspection routine that always answers "nothing found" is worse than one that
refuses, because a caller has no way to tell the two apart.

**Fix:** use the interference-detection manager instead. `GetInterferenceCount` is an
ordinary return value, so `0` is a measurement rather than a swallowed failure:

```python
manager = sw_type_info.flagged(
    assembly.InterferenceDetectionManager, "IInterferenceDetectionMgr"
)
manager.TreatCoincidenceAsInterference = False
manager.IncludeMultibodyPartInterferences = True
try:
    count = int(manager.GetInterferenceCount() or 0)
    interferences = manager.GetInterferences() if count else None
finally:
    manager.Done()      # leaves the assembly out of interference-display mode
```

Measured on the same two assemblies: two coincident copies of a 32000 mm³ block gave
`GetInterferenceCount() -> 1` and `GetInterferences()` a 1-tuple; moving one copy 100 mm
away gave `0` and `None`.

Call `Done()` from a `finally` — a failed read otherwise leaves the assembly in
interference-display mode.

Found 2026-08-14 while implementing `check_interference` against a live SolidWorks 2025
session (gen_py wrapper `83A33D31-…x0x33x0`).

---

## 14. `IInterference.Components` is a property, not a method

**Symptom:** `AttributeError: GetInterferences.GetComponents`, or
`com_error: (-2147352562, 'Invalid number of parameters.', None, None)` from
`IGetComponents`.

**Root cause:** `IInterference` exposes its components as the **property**
`Components`. There is no `GetComponents()` on the interface at all, and
`IGetComponents(n)` — which the type library declares as taking a component count —
rejects that argument. Same late-binding member ambiguity as #5, reached from the
opposite direction.

**Fix:**

```python
item = sw_type_info.flagged(raw_interference, "IInterference")

volume_m3 = item.Volume                 # property, cubic metres
component_count = item.GetComponentCount()   # method, takes ()
components = item.Components            # property — no (), and not GetComponents()

for component in components:
    name = sw_type_info.flagged(component, "IComponent2").Name2
```

`Volume` is worth reading: it is the overlap volume in cubic metres and makes an
independent check possible. Two exactly coincident copies of a 32000 mm³ part reported
`3.2000000000000005e-05` m³ — the whole part volume, as it must be.

Found 2026-08-14 alongside #13.

---

## 15. Default template slots are 8, 9 and 10 — slots 0–3 are empty

**Symptom:** `NewDocument` fails, or a new-document helper reports "failed to create"
with no further detail.

**Root cause:** `ISldWorks::GetUserPreferenceStringValue` returns an empty string for the
low slot numbers on SW 2025. Code that reads slot `0` or `1` for a template path passes
`""` straight into `NewDocument`, and every operation downstream of it fails at the first
step. Measured on SW 2025:

| Slot | Value |
|---|---|
| 0, 1, 2, 3 | `''` (empty) |
| 6 | `…\SOLIDWORKS 2025\templates\` (directory) |
| 7 | `…\lang\english\sheetformat` (directory) |
| **8** | `…\templates\Part.prtdot` |
| **9** | `…\templates\Assembly.asmdot` |
| **10** | `…\templates\Drawing.drwdot` |

**Fix:** probe the document-specific slot first and fall back, and check the extension
and that the file exists rather than trusting the first non-empty string:

```python
for index in (10, 1, 0, 2, 3):        # drawing; use (8, …) part, (9, …) assembly
    template = app.GetUserPreferenceStringValue(index)
    if template and template.lower().endswith(".drwdot") and os.path.exists(template):
        break
else:
    raise Exception("No drawing template configured in SolidWorks")
```

A fallback of the form `GetUserPreferenceStringValue(0).replace("Part", "Drawing")` is
worth calling out as a trap: on SW 2025 slot 0 is empty, so the replace runs on `""` and
produces `""`, and the failure surfaces far from its cause.

Found 2026-08-14 while implementing drawing-view placement against live SolidWorks 2025.

---

## 16. `AddComponent5` places nothing unless the component document is already loaded

**Symptom:** the call returns a component object, the assembly is unchanged, and nothing
raises.

**Root cause:** two independent failures that look identical.

1. The component document must be open in memory before it can be inserted. `OpenDoc6`
   has to run first.
2. `OpenDoc6`'s `errors`/`warnings` out-parameters must be **byref VARIANTs**. Passing
   `pythoncom.Missing` makes it return `None`, the document stays unloaded, and every
   `AddComponent` overload then does nothing — while still handing back a component
   object, so the return value looks like success. (Runbook item 1 in `CLAUDE.md` at the
   repository root recommends `pythoncom.Missing` for `OpenDoc6`; that works for opening a
   document to read it, but not on this path.)

A third cause produces the same silence: SolidWorks refuses to insert a part with no
solid body, again without raising.

**Fix:** load first with byref out-params, then verify by component count rather than by
the return value:

```python
def _byref_int():
    return win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

opened = app.OpenDoc6(path, doc_type, 1, "", _byref_int(), _byref_int())
if not opened:
    raise Exception(f"Could not load {path!r} — OpenDoc6 returned nothing.")

before = len(assembly.GetComponents(True) or ())
assembly.AddComponent5(path, 0, "", False, "", x_m, y_m, z_m)
after = len(assembly.GetComponents(True) or ())
if after <= before:
    raise Exception("Component was not inserted — check the part has a solid body.")
```

Found 2026-08-14 while implementing assembly component insertion against live
SolidWorks 2025.

---

## 17. Use `AddMate5` on SW 2025, not `AddMate3`

**Symptom:** older mate examples and third-party plans call `IAssemblyDoc::AddMate3`.

**What works:** `AddMate5` — 15 arguments, with `ErrorStatus` as a byref out-parameter
(use the same `_byref_int()` helper as #16). Verified live on SW 2025 by confirming the
mate moved geometry, not by its return value: snapshot every component's
`IComponent2::Transform2` before and after and compare. SolidWorks accepts a mate it then
ignores, so the return value alone does not tell you whether anything moved.

Found 2026-08-14 while implementing assembly mates against live SolidWorks 2025.

---

## 18. `InsertModelAnnotations3` inserts nothing — unresolved

**Status: open question.** Recorded so the next person does not repeat the search. If you
know the missing ingredient, please correct this entry.

**Symptom:** `IDrawingDoc::InsertModelAnnotations3` returns `None` and no dimensions
appear, on a drawing view of a part that carries a real sketch dimension.
`IView::GetDisplayDimensionCount()` stays `0`.

**What was tried**, all on SW 2025, all returning `None`:

- `Types` as `swInsertDimensions` (8) and as `swInsertDimensionsMarkedForDrawing` (32768),
  and the two OR'd together
- `AllViews` both `True` and `False`
- with the view selected via `SelectByID2(name, "DRAWINGVIEW", …)` — using a
  `VT_DISPATCH` null callout per #1, which is what makes the selection return `True` —
  and then activated with `ActivateView`, following the sequence in the official example
- against both a `*Front` and a `*Top` view, in case the dimension's sketch plane could
  not be shown in the chosen view
- against a part with an explicit sketch dimension added through
  `ISketchManager`, not just an undimensioned profile
- after `ForceRebuild3(True)`
- called raw rather than through a helper that swallows exceptions, confirming it
  genuinely returns `None` rather than raising

**Do not** infer a count from the return value if you get one: the method returns an
**array of inserted `IAnnotation` objects**, so `int(result)` is meaningless and
`len(result)` is the count. A reference implementation read it as an integer and
therefore always computed `0`.

Found 2026-08-14 while implementing drawing annotation against live SolidWorks 2025.

---

## Adapter wiring traps — not COM, same silent-failure shape

These are not SolidWorks issues, but they fail the same way: the code imports, the tests
pass, and the thing you wrote never runs.

### A method written at module scope in a mixin file is unreachable

`adapters/solidworks/io.py` defines `SolidWorksIOMixin`. A method accidentally left at
module scope — one indentation level out — still imports cleanly, still passes every
mock-adapter test, and still satisfies "does this capability exist on every layer" checks.
But `PyWin32Adapter` then resolves the name to `SolidWorksAdapter`'s "not implemented"
default, so every call returns that error and the COM implementation never executes.

Nothing in a normal test run catches this. Assert the owning class directly:

```python
owner = next(
    (klass.__name__ for klass in PyWin32Adapter.__mro__ if name in vars(klass)),
    None,
)
assert owner == "SolidWorksIOMixin"
```

### `_attempt(..., default=X)` hides the difference between "returned nothing" and "raised"

The adapter's `_attempt` helper swallows the exception and hands back the default, so a
`None` result has two very different meanings. When diagnosing a COM call that "returns
`None`", call it raw and catch explicitly before drawing any conclusion:

```python
try:
    raw = drawing.InsertModelAnnotations3(0, 8, True, True, False, False)
    print("returned", type(raw).__name__, raw)
except Exception as exc:
    print("raised", type(exc).__name__, exc)
```

Both investigations behind #13 and #18 came close to the wrong conclusion because a
swallowed `TypeError` was indistinguishable from a genuine empty result.

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
