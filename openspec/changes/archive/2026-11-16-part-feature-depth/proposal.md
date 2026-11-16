## Why

An agent can extrude, cut, revolve, sweep, loft, fillet, chamfer and
pattern around an axis, but it can't make the features most real parts
need next: a standard tapped or counterbored hole, a thread, a row of
features, a hollowed body, drafted walls for moulding, or a rib. The
closest comparable server leads with holes and threads, so this is where an
agent comparing the two finds us short. An agent working without these
draws a circle at a guessed size and cuts it, which gives no thread data,
no standard callout in a drawing, and a part that doesn't match the
fastener. Issue #105 (convert entities) was hit live: an agent couldn't
sketch on an existing edge and cut in the wrong place.

## What Changes

- **`create_hole`**: a Hole Wizard hole (simple, counterbored,
  countersunk or tapped) of a standard size (`M6`, `#10`, ...) on a flat
  face, at a point on that face, blind to a depth or through all.
- **`add_cosmetic_thread`**: a cosmetic thread on a cylindrical edge picked
  by a point, to a standard size and depth (or through), so a drawing shows
  the thread callout.
- **`pattern_linear`**: repeats features along one or two directions given
  by edges or axes, with count and spacing, like `pattern_circular`.
- **`create_shell`**: hollows the active body to a wall thickness, with the
  faces to remove picked by points, inward or outward.
- **`add_draft`**: drafts faces picked by points by an angle against a
  neutral plane or face.
- **`create_rib`**: a rib from an open sketch, of a thickness, on one or
  both sides of the sketch.
- **`sketch_convert_entities`**: projects edges (picked by points) or a
  face's outline into the open sketch, as normal or construction
  geometry, and returns the new entities' ids (#105).
- Each solid-changing tool replies with `measured_change`, as the extrude
  tools do, and fails when the volume does not change.

## Capabilities

### New Capabilities

- `tools/hole-wizard`: `create_hole` makes a standard hole at a point on a
  flat face.
- `tools/cosmetic-thread`: `add_cosmetic_thread` adds a thread to a
  cylindrical edge.
- `tools/shell-draft-rib`: `create_shell`, `add_draft` and `create_rib`
  shape an existing body.
- `tools/sketch-convert-entities`: `sketch_convert_entities` copies model
  edges into the open sketch.

### Modified Capabilities

- `tools/feature-patterns`: `pattern_linear` joins `pattern_circular` and
  `mirror_feature` under the volume-change rule.
- `tools/measured-feature-change`: the new solid tools report
  `measured_change`.

## Impact

- **COM and adapter code, all on the connect thread inside
  `_handle_com_operation`:**
  - `adapters/solidworks/features.py`: `IFeatureManager.HoleWizard5`,
    `InsertCosmeticThread3`, `FeatureLinearPattern5`,
    `InsertMultiFaceDraft`, `InsertRib`, and `IModelDoc2.InsertFeatureShell`;
  - `adapters/solidworks/sketch.py`: `ISketchManager.SketchUseEdge3`;
  - face and edge picks through `face_selection.py` (`ForceRebuild3`
    first, `SelectByID2` with a `VT_DISPATCH` null callout: runbook #11,
    #13).
  - Seven new adapter methods through `base.py`, `circuit_breaker.py`,
    `connection_pool.py` and `mock_adapter.py`.
- **Tools:** `modeling.py` (six tools), `sketching.py`
  (`sketch_convert_entities`), `tool_hints.py`, `support_levels.py`.
- **Docs:** tool catalog pages, the agent skill's workflow notes (hole
  before thread, convert then cut), `docs/planning/solidworks-api-coverage.md`
  section 3.7, CHANGELOG, regenerated progress bars.
- **Live tests:** one bundle at the end; `HoleWizard5`'s 27 arguments are
  checked live before the tool's inputs are fixed (design decision 2).
- Closes #105. Sheet metal (#57) is queue item 15, not this change.
- **Depends on the honest-tool-list change (queue item 10)**, merged
  first: the tool names follow its verb list.
