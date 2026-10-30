## Context

See proposal.md for motivation and the three specs for behaviour. Today's
read paths, and the constraints they put on this change:

- **`get_mass_properties`** (`solidworks/io.py`) starts with
  `ForceRebuild3(False)`. That clears the live selection (pitfall #23), so it
  cannot be reused for a "before" reading.
- **`get_model_info.feature_count`** is `FeatureManager.GetFeatureCount(True)`.
  That total includes the origin, the default planes and folders, so an agent
  cannot predict it.
- **`list_features`** returns raw `GetTypeName2` values per feature, which is
  enough to filter modelling features.
- **`list_components`** returns top-level component names.
- **`check_interference`** returns `interference_found`, which is `None` in
  the mock.
- **No adapter reads** a bounding box, solid-body count or mate count.
- **The mock adapter** returns random mass values, has no geometry, and does
  not track mates.
- **Wrappers:** `circuit_breaker.py` and `connection_pool.py` wrap every
  adapter method by hand, so a new method needs explicit forwarding in both.

## Goals / Non-Goals

**Goals:**
- One verification call usable as the final step of any build.
- A selection-safe summary read that is cheap enough to run twice around
  every solid feature.
- Honest results in mock mode: `null`, never fabricated passes.

**Non-Goals:**
- Inline measurement for fillet, chamfer, pattern, `insert_component` and
  `add_mate`. Same pattern, but those tools consume selections differently.
  That is a follow-up once the three solid-feature tools have proven it live.
- Per-component verification inside an assembly (open the part and verify it).
- Checking dimensions or sketch geometry; `get_dimension` and
  `check_sketch_fully_defined` already exist.
- Making the mock adapter simulate geometry.

## Decisions

### D1. One new adapter read, everything else reused
`verify_model` composes these reads:
- `get_model_geometry_summary` (new);
- `get_mass_properties`, for mass, only when `mass_kg` is expected;
- `list_features`, only when `feature_count` is expected;
- `check_interference`, only when `no_interference` is expected.

Skipping reads that no expectation needs keeps the common case fast, and
avoids `get_mass_properties`' rebuild unless mass was asked for. The
`measured` block holds only what was read, plus the summary.

*Alternative:* one monolithic adapter `verify` method. Rejected: it would
duplicate the mass, feature and interference logic per adapter and bypass
existing fixes (pitfalls #13 and #14).

### D2. Volume comes from the summary, not `get_mass_properties`
The summary reads volume through `Extension.CreateMassProperty()` without a
rebuild. Volume is geometric and independent of material. Mass depends on
the assigned material: SolidWorks falls back to its default density when
none is assigned. The `mass_kg` check therefore reports the material name in
its `note` when the adapter can read it, so a mismatch caused by a missing
material is obvious.

### D3. Bounding box: tight per-body extreme points for parts, assembly box for assemblies
- **Parts.** `IPartDoc.GetPartBox` and `IBody2.GetBodyBox` can be loose on
  curved geometry. For parts, take the six `IBody2.GetExtremePoint(±x, ±y, ±z)`
  points of each solid body and combine them. `bounding_box_method` is
  `"extreme_points"`.
- **Parts fallback.** If extreme points fail, fall back to `GetPartBox(True)`,
  reported as `"part_box"`.
- **Assemblies.** Use `IAssemblyDoc.GetBox(0)`, reported as `"assembly_box"`.
  Per-component extreme points would need every component transform, and
  that's not worth it for v1.

The default `length_tolerance_mm` (0.1) suits extreme points. The tool
docstring tells agents to widen it when the method is `assembly_box`.

*Alternative:* always `GetPartBox`. Rejected: a 360° revolve of a Ø20 shaft
can report a box several percent larger than 20, which would make the
bracket demo's shaft check fail falsely. The live test (task 7) measures a
cylinder with both methods to confirm the difference.

### D4. Solid-body count and mate count
- **Bodies.** `IPartDoc.GetBodies2(swSolidBody=0, VisibleOnly=False)`, as in
  `save_body_as_part`. For an assembly, the solid-body count is left `null`
  rather than summing component bodies; it is not a meaningful expectation
  there.
- **Mates.** Walk the top-level tree for the feature whose `GetTypeName2` is
  `"MateGroup"`. Then count its sub-features (`GetFirstSubFeature` /
  `GetNextSubFeature`, flagged as in `rebuild_inspector.py`), skipping
  suppressed ones.
- **Components.** The count reuses the existing `_component_names` helper.

### D5. Feature-count filter
These are excluded by `GetTypeName2`:
- `ProfileFeature` and `3DProfileFeature` (sketches);
- `OriginProfileFeature`;
- any type ending in `Folder`;
- `DetailCabinet`, `MaterialFolder`, `MateGroup`, `HistoryFolder` and
  `SensorFolder`;
- the first three `RefPlane` entries in tree order. The default planes are
  always first, and filtering by position works regardless of locale, unlike
  matching "Front Plane".

The filter is a pure function in `tools/analysis.py`, so it is unit-tested
against both mock and recorded-live descriptor lists. Counted names are
returned (spec: "Counted features are listed") so any disagreement is visible
rather than silent.

### D6. Verdict and payload
`status` reflects whether the tool ran; `verdict` reflects whether the model
matched. Failure to match is the tool's normal output, not an error, so it
does not go through the error boundary. Shape:

```
{status, message, verdict, checks: [{name, expected, actual, tolerance, unit, passed, note}],
 measured: {...}, execution_time}
```

`message` summarises, e.g. "Verification failed: 3 of 4 checks passed
(failed: volume_mm3)". Relative tolerance compares
`abs(actual - expected) <= tol * abs(expected)`, so an expected 0 needs an
actual of exactly 0. The summary rounds volume to 0.0001 mm³, so "nothing
there" reads as exactly 0.

### D7. Invalid-input handling goes through the boundary
These raise `InvalidInputError`:
- an assembly-only expectation on a part;
- a negative tolerance;
- a drawing as the active document.

The adapter's own errors (no active model) go through `require_success`.
No `try/except` in the tool.

### D8. Measured change: two summary reads around the adapter call
In each of the three tools:
1. Before calling the adapter's feature method, read the summary. The base
   implementation returns an error result, so an adapter without the read
   needs no special case: an error simply means "not measured", and
   `measured_change` is omitted.
2. After success, read it again.
3. Build `measured_change` with a small helper, `_measured_change(before,
   after)`.

A failed read yields `null` fields and a `note`, never an exception. That is
an `AdapterResult` status check, not a `try`.

**Ordering:** the "before" read happens before the adapter selects the sketch.
The extrude and cut paths clear the selection and re-select the sketch by
name themselves, so even a selection-disturbing read would be harmless here.
The summary is still specified as selection-safe so it can later wrap
selection-consuming tools (fillet, chamfer).

**Zero-volume warning:** when `volume_delta_mm3 == 0` on a successful feature,
the reply gains `warning`. This is the silent-no-op shape of pitfall #19
surfaced to the agent.

### D9. Mock adapter
- `get_model_geometry_summary` returns `null` for volume, box and bodies.
- For assemblies it returns `len(self._components)` and `len(self._mates)`.
- `add_mate` appends to `self._mates`, which is reset with the document like
  `_components`.

Tool tests that need numbers monkeypatch the adapter's summary, mass and
interference reads with fixed values, rather than teaching the mock fake
geometry.

### D10. Settle cost
Each COM read pays the 0.25 s settle pause, so the measured change adds about
0.5 s per extrude, revolve or cut. That is acceptable against the 1–3 s a
feature already takes, and it is what makes silent no-ops visible. There is
no opt-out flag in v1; one can be added if batch users ask.

## Risks / Trade-offs

- **[Risk] `CreateMassProperty` may itself touch the selection,** e.g. compute
  on selected bodies only. → Mitigation: the live test selects an edge, reads
  the summary, and asserts the selection count is unchanged and the volume
  equals the whole-part volume. If it fails, read the volume from the body
  list instead (sum of `IBody2.GetMassProperties(0)[3]`), still with no
  rebuild.
- **[Risk] `GetExtremePoint` signature or out-params misbehave under late
  binding.** It returns its point via ByRef out-params (pitfall #25 shape).
  → Mitigation: probe it non-destructively in the first live session on a
  scratch part. The part-box fallback means the read still returns a value,
  labelled with its method.
- **[Risk] The mate group's sub-feature walk counts non-mate children,** such
  as mate folders on newer SW versions. → Mitigation: count only sub-features
  whose type starts with `Mate` or is a known mate type, and recurse one level
  into folders. Covered by the live assembly test.
- **[Risk] The "no rebuild" summary reads stale geometry** if called mid-edit.
  → Mitigation: after a feature call, SolidWorks has already rebuilt. The
  verify tool documents that the model should be rebuilt first, and reports
  the rebuild status from `get_model_info` when available.
- **[Trade-off] The default 1 % relative tolerance** may be too tight for
  hand calculations of filleted parts. It is caller-overridable, and the
  docstring tells agents to widen it when fillets or chamfers are present.

## Migration Plan

Additive only. No config, schema or payload removals. Rollback is reverting
the PR. The tool count rises to 152 in docs and server metadata.
