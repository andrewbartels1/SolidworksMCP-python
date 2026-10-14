## Context

- `list_drawing_views` is already declared on every adapter layer (base,
  circuit breaker, connection pool, mock, real). Only the tool wrapper is
  missing.
- `rebuild_model` exists only on the real `io.py` mixin. It returns `None`
  data and calls `ForceRebuild3(False)`.
- `select_feature` exists on the real `selection.py` mixin and the mock. It
  is not in `base.py`, `circuit_breaker.py` or `connection_pool.py`.
- The real `select_feature` delegates to `FeatureSelector` in
  `pywin32_adapter.py`. It tries three strategies in order:
  1. `Extension.SelectByID2` over the candidate names × entity types
  2. component `Select4`/`Select`/`Select2`
  3. a feature-tree walk with `Select2`

  When all of them fail it returns `{"selected": False}` as SUCCESS.
- `try_select_by_extension` passes `None` as the `Callout` argument. That
  raises `Type mismatch` (CLAUDE.md pitfall #11), and the bare
  `except: continue` hides it.
- The live probe on 2026-10-13 returned `selected: False` for
  `Boss-Extrude1`, which means strategy 3 also failed. The likely cause is
  late-binding resolution on unflagged dispatches; task 1.1 confirms it.
- Pieces that already exist and can be reused:
  - `features._select_feature_by_name`: `ClearSelection2` → `FeatureByName`
    → `IFeature::Select2(False, 0)`. Proven live for
    suppress/unsuppress/delete/rename.
  - `features._select_edge_by_coord(..., entity_type="FACE")`: selects a
    face by a point, with a correct `VT_DISPATCH` null callout and a
    tessellation rebuild. Proven live for `add_chamfer`'s `face:` spec.
  - `get_selected_entities` (#112): describes the selected faces and edges
    (bbox, normal, endpoints, length).
  - `add_chamfer`/`add_fillet` with empty `edge_names` act on the live
    selection (#112).

### Live probe findings (R2026x, 2026-10-13, tasks 1.1-1.3)

- **select_feature**: `SelectByID2` with `None` callout -> `Type mismatch`
  for every name; with `_null_callout()` -> True for `Boss-Extrude1`,
  `Sketch1`, `Front Plane`. `FeatureByName(...).Select2(False, 0)` -> True
  for all three. The tree-walk strategy fails because unflagged
  `IFeature.GetNextFeature` resolves as a property -> `Member not found`;
  `flagged(feature, "IFeature")` fixes it. So all three strategies were
  broken, two by known pitfalls (#11 and method flagging).
- **Rebuild diagnostics** (error induced by emptying an extrude's sketch ->
  `Boss-Extrude2` code 1, not a warning):
  - `IModelDocExtension.GetWhatsWrongCount()` works (method).
  - `GetWhatsWrong(vf, vc, vw)` works late-bound when each out-param is
    `VARIANT(VT_BYREF | VT_VARIANT, None)`; `.value` then holds the feature
    tuple, code tuple and warning-bool tuple. `pythoncom.Missing` fails
    ("can not be converted to a COM VARIANT"); no args -> "Parameter not
    optional". **Chosen source: (a) GetWhatsWrong**; (b)
    `IFeature.GetErrorCode2(VARIANT(VT_BYREF|VT_BOOL, False))` also works and
    is the fallback. No early-bound wrapper is needed (makepy auto-generation
    is unavailable for these objects anyway).
  - `IFeature.GetParents()`, `GetTypeName2()` work flagged.
  - Changing a fillet's radius dimension to 30/200 mm on a 10 mm box via
    `SetSystemValue3` + `EditRebuild3` produced **no** reported error, so the
    live "rebuild with errors" test uses the empty-sketch method instead.
- **Faces/edges**: every dispatch must be flagged (`IBody2`, `IFace2`,
  `ISurface`, `IEdge`, `ICurve`, `IEntity`, `ISelectionMgr`); unflagged,
  `GetEdges`/`GetArea`/`IsPlane` resolve as properties (value returned,
  `'tuple' object is not callable`) and `GetSurface` is `Member not found`.
  - `IFace2.Normal` is a property; it is `[0,0,0]` for non-planar faces.
  - `ICurve.CircleParams` (property) = `[cx, cy, cz, ax, ay, az, radius]` in
    metres for circles; `None` for lines.
  - `IRefPlane.Transform.ArrayData` = 3x3 rotation + translation + scale
    (Front Plane is identity); the plane normal is the rotated Z axis
    (verify against Top/Right in the live test).
  - `IFace2.GetClosestPointOn(x, y, z)` (metres) returns 5 values; the first
    three are the closest point on the face, so "point is on face" =
    distance(query, closest) within tolerance. Works for planar and
    cylindrical faces. Used for `point` mode instead of a UI pick, so the
    existing selection is untouched when `append=true`.
  - `IRefPlane.Transform.ArrayData`: the plane normal is elements `[6:9]`
    and the origin `[9:12]` (Front -> (0,0,1), Top -> (0,1,0), Right ->
    (1,0,0), all through the origin). Confirms the side aliases.
  - A full-circle edge (hole rim) has no start/end vertex
    (`GetStartVertex()` -> `None`); describe it by `CircleParams` centre and
    radius instead.
  - **SolidWorks crashed** inside `FeatureExtrusion3` after ~10 back-to-back
    probe runs (some destructive) against a long-lived session. Further live
    runs: one batched pass (task 12) with `SW_TEST_PACE_SECONDS=4`, user
    approval first.
  - `IEntity.Select4(append, selectData)` needs a real
    `ISelectionMgr.CreateSelectData()` object; `None` -> `Type mismatch`
    (same family as pitfall #11). Two appended edge selects -> count 2.

## Goals / Non-Goals

**Goals:**
- Four tools that follow the existing tool contract: strict Pydantic input,
  a stable `status`/`message`/`execution_time`/data shape, errors returned
  rather than raised.
- `select_feature` that really selects, never reports a false success, and
  can append.
- `select_face_edges` that turns "all the (circular) edges on the top face"
  into a live multi-selection that `add_chamfer`/`add_fillet` can consume.
- Rebuild diagnostics an LLM can act on: which feature, which error, what it
  references, and what to do about it.
- Full adapter-chain parity, so the tools work through the
  circuit-breaker/pool wrappers.

**Non-Goals:**
- Selecting edges by arbitrary predicates beyond `edge_type`, for example
  "edges longer than 10 mm" or "concave only". `edge_type` covers the stated
  chamfer/fillet use; the filter is an enum that can grow later.
- Face selection in assemblies (component bodies). Parts only, for now.
- Automatically repairing rebuild errors. Hints guide the LLM; they don't
  act.
- A CI lint that keeps the adapter and tool surfaces in sync (out of scope
  per #106).
- The circuit-breaker reset tool (#115, queued separately).

## Decisions

1. **Selection strategy order: name lookup first (Open/Closed).** Add
   `FeatureSelector.try_select_by_feature_name` as the first strategy. It
   delegates to `features._select_feature_by_name`, which is generalized to
   take `append` (it only clears the selection when `append` is false), so
   there is one "select by name" implementation. The existing strategies
   stay as fallbacks for components, planes and mates.
   *Alternative considered:* replacing the chain outright. Rejected because
   the component path is the only route for assembly components, and
   `preview_service` relies on it.
2. **Fix the callout in `try_select_by_extension`.** Reuse `_null_callout()`
   from `features.py`, the existing pitfall-#11 helper. Thread `append`
   through as `SelectByID2`'s `Append` argument.
3. **Not found is an ERROR at the adapter boundary.** `selection.py` maps
   an unselected payload to `ERROR "Feature not found or could not be
   selected: <name>"`. `FeatureSelector.select_feature` stays a pure payload
   producer, which keeps it easy to unit-test. `selection_count` is read
   back from `ISelectionMgr::GetSelectedObjectCount2(-1)`.
4. **`select_face_edges`: single responsibility split.**
   - A *face resolver* turns one of `point`/`side`/`plane` into an `IFace2`
     (pure-ish functions in `adapters/solidworks/face_selection.py`):
     - `point`: `_select_edge_by_coord(entity_type="FACE")`, then read the
       face back from the selection manager. This reuses the proven pick
       path.
     - `side`: iterate `IPartDoc.GetBodies2(swSolidBody)` → `IBody2.GetFaces`.
       Keep planar faces (`IFace2.IGetSurface().IsPlane()`) whose `Normal`
       has dot product ≥ 0.999 with the side vector. Pick the one with the
       largest projection of its bbox centre on that vector. Ties go to the
       larger area.
     - `plane`: `FeatureByName(plane)` → `IRefPlane` transform gives the
       plane origin and normal. Pick the planar faces whose normal is
       parallel to the plane and whose centre lies on the plane within
       1e-6 m. If several faces lie on the plane, select the edges of all of
       them and report every face.
   - An *edge collector* calls `IFace2.GetEdges()` and filters by
     `edge_type` using `IEdge.GetCurve()` → `ICurve.IsCircle()` /
     `IsLine()`. Each edge is described with the same field set as
     `get_selected_entities` (shared helper, not copy-paste), plus `radius`
     for circles via `ICurve.CircleParams`.
   - A *selector* calls `IEntity.Select4(append_i, selectData)` on each edge.
     The first edge uses `append` from the input and later edges use True,
     with a `ClearSelection2` first when `append=false`. Afterwards
     `selection_count` is read from the selection manager and checked
     against the edge count. A mismatch is an ERROR naming the edges that
     did not select.
   - Side aliases follow SolidWorks' default orientation (Front = XY plane
     with normal +Z, Top = XZ with +Y, Right = YZ with +X). That gives
     `front=+Z`, `back=-Z`, `top=+Y`, `bottom=-Y`, `right=+X`, `left=-X`.
5. **Rebuild diagnostics.**
   - `rebuild_model(top_level_only=False)` calls
     `ForceRebuild3(top_level_only)`. **Revised after the live run
     (2026-10-13):** `ForceRebuild3` returns False whenever *any* feature
     fails, so False is not treated as "the rebuild call broke". The issues
     are collected either way, and a generic "rebuild failed" ERROR is
     returned only when SolidWorks reports False but names no failing
     feature. `data.rebuilt` carries the raw return value.
   - It then collects diagnostics through the first source that works live
     (task 1.2 decides the order):
     - (a) `IModelDocExtension::GetWhatsWrong(Features, ErrorCodes,
       Warnings)`, which uses ByRef arrays
     - (b) a feature-tree walk calling `IFeature::GetErrorCode2(IsWarning)`
       (ByRef bool). If late binding cannot do out-params, use a targeted
       `gencache` early-bound wrapper for that one call only, not for the
       whole adapter. That keeps the "late binding forced" invariant
       everywhere else.
     - (c) obsolete `IFeature::GetErrorCode()`, which returns only the code.
       Severity is then derived from the code's enum name, and the warning
       flag is unknown.
   - Every feature entry carries:
     - `feature`: name
     - `type`: from `GetTypeName2`
     - `code`
     - `code_name`: from a `swFeatureError_e` map generated from
       `swconst.tlb`
     - `severity`
     - `description`
     - `parents`: names from `IFeature::GetParents()`
     - `hint`
   - **Enum source.** The `swFeatureError_e` map is generated once from
     `swconst.tlb` (`pythoncom.LoadTypeLib`, the same approach as #95) and
     committed as a static Python table (`sw_feature_errors.py`). Runtime
     never depends on the TLB, and the mock/CI can use it. Values are never
     hand-typed (lesson from #60).
   - **Hints.** A curated dict covers the common codes: missing or
     unresolved edge/face references, sketch issues (open or
     self-intersecting profile, dangling relations), zero-thickness or
     invalid geometry, and pattern seed problems. Any other code gets a
     generic hint: "inspect the parents listed, re-target references, or
     suppress/delete and recreate".
   - **Status.** Any entry with `severity == "error"` gives an ERROR
     `AdapterResult` that still carries `data`. Warnings only give SUCCESS.
     The tool passes `data` through on both paths. This is a small,
     deliberate extension of the tool error shape: `data` alongside
     `status`/`message`.
6. **Interface placement.** In `base.py`, `select_feature`,
   `select_face_edges` and `rebuild_model` get concrete defaults that return
   "not implemented" ERRORs, the same pattern as `list_drawing_views`.
   `circuit_breaker.py` (per-operation buckets) and `connection_pool.py`
   get pass-throughs that follow their per-method pattern.
7. **Tool placement and inputs.**
   - `list_drawing_views` goes in `tools/drawing.py` and takes no input.
   - `rebuild_model`, `select_feature` and `select_face_edges` go in
     `tools/modeling.py`, with these inputs:
     - `RebuildModelInput(top_level_only: bool = False)`
     - `SelectFeatureInput(feature_name: str, append: bool = False)`, where
       the name is stripped and must be non-blank
     - `SelectFaceEdgesInput(point: list[float] | None, side: str | None,
       plane: str | None, edge_type: Literal["all","linear","circular"] =
       "all", append: bool = False)`. A model validator enforces exactly
       one of point/side/plane, `point` length 3, and that `side` is one of
       the 12 accepted tokens (case-insensitive).
8. **Mock parity.**
   - `select_feature` succeeds only for tracked names and tracks a
     selection list so `append` and `selection_count` behave.
   - `select_face_edges` returns canned faces for the six sides of the mock
     box and reports `circular` edges only when a hole/cut feature exists.
     Unknown planes and out-of-body points are errors.
   - `rebuild_model` returns a clean result, or ERROR with no model. A test
     hook can inject a fake failing feature so the error path is
     exercised.

## Risks / Trade-offs

- **Out-parameter APIs under forced late binding** (`GetWhatsWrong`,
  `GetErrorCode2`, `CircleParams`, `IRefPlane` transform). Mitigation: task
  1.2 tries each live before any code is written. The targeted early-bound
  fallback is limited to the one call and recorded in
  `com-api-pitfalls.md`.
- **The tree-walk failure in `select_feature` isn't explained yet.**
  Mitigation: task 1.1 reproduces it. The fix doesn't depend on it, since
  the new first strategy is proven live.
- **Choosing a face by `side` with non-planar or stepped tops.** "Top" is
  the furthest planar face with a +Y normal. On a stepped part, a lower
  +Y-facing ledge is intentionally *not* chosen. The tool reports which
  face it chose (`data.face`), so the LLM can switch to `point` when it
  meant another one.
- **Selection is UI state, which the user can change mid-chain.** A user
  clicking between `select_face_edges` and `add_chamfer` changes what gets
  chamfered. This is documented in the tool docstrings. The chamfer result
  already reports its edges.
- **ERROR-on-not-found changes internal behavior.** Only `preview_service`
  calls `select_feature`, and it already tolerates a failed result. Old
  tests are updated deliberately.
- **Scope grew (4 tools, not 3).** Accepted by the user on 2026-10-13 rather
  than splitting `select_face_edges` into its own change. Sign-off is still
  one tool at a time, from the live evidence in task 11.

## Code review follow-ups (2026-10-13, before PR)

A high-effort `/code-review` of the implementation found ten issues, all fixed
and unit-tested before live re-certification (5/5 live):

1. A qualified name (`Front Plane@Part1-1@Assem1`) no longer short-circuits
   through `FeatureByName`, which drops the qualifier. The name-first strategy
   runs only for bare names or names qualified with the active document's
   own title.
2. The circuit breaker no longer counts `rebuild_model` / `select_feature` /
   `select_face_edges` ERROR *answers* as failures
   (`error_results_are_failures=False`). Only exceptions trip it, so the
   diagnostic tool cannot lock itself out while a model is broken.
3. A partial `select_face_edges` failure clears the selection before
   erroring, so `add_chamfer(edge_names=[])` can never act on a partial set.
4. Extra `GetWhatsWrong` warning flags are trimmed, not fatal.
5. `ForceRebuild3` False + warnings only -> ERROR that keeps the warnings in
   `data`.
6. The fallback tree walk also visits sub-features (sketches under
   extrudes/cuts).
7. / 8. Shared `com_utils.py` (attempt, targeted flagging, list coercion,
   selection count, error-prefix stripping) replaces three private copies.
9. The mock clears its selection whenever the active document changes.
10. New tools' error payloads include `execution_time`.

The live run also showed `GetTypeName2` reports a boss extrude as `ICE`; the
hint/label tables now treat `ICE` as a generic extrude.
