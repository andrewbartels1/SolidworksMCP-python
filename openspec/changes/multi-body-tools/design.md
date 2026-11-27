## Context

Motivation: see proposal.md, under "Why".

**What exists:**
- A multi-body part is made with `create_extrusion` (`merge_result: false`)
  and read in three places:
  - `io.py` `_solid_bodies` (`IPartDoc.GetBodies2(swSolidBody, False)`,
    each wrapped as `IBody2`);
  - `save_body_as_part`, which matches `IBody2.Name`;
  - `features.py`.
- `part_features.py` `_measured` judges a feature by the volume before and
  after, and deletes one that changed nothing. The helix branch, not yet
  merged, adds `direction` to it.
- Body names change as features run: a combine renames its result, and a
  split names new bodies after the split feature.

**From the installed type library (2026):**
- `IFeatureManager.InsertCombineFeature(OperationType, MainBody: IBody2,
  ToolVar: Variant)` returns `IFeature`. `OperationType` is
  `swBodyOperationType_e`: SWBODYINTERSECT 15901, SWBODYCUT 15902,
  SWBODYADD 15903.
- `IFeatureManager.PreSplitBody2()` returns the bodies the selected trim
  tool would make.
- `IFeatureManager.PostSplitBody2(BodiesToMark, ConsumeCut, Origins,
  SavePaths, OverrideTemplateName)` returns the feature.
- `IFeatureManager.InsertMoveCopyBody2(TransX, TransY, TransZ, TransDist,
  RotPointX, RotPointY, RotPointZ, RotAngleX, RotAngleY, RotAngleZ, BCopy,
  NumCopies)` acts on the selected bodies.
- `IFeatureManager.InsertDeleteBody2(KeepBodies)` acts on the selected
  bodies.
- `IFeatureManager.InsertScale(Type, Uniform, X, Y, Z)`. `Type` is
  `swScaleType_e`: centroid 0, origin 1, coordinate system 2.

## Goals / Non-Goals

**Goals:**
- Name bodies one way everywhere.
- Prove each operation by measuring it.
- Keep the COM work in one module, on the connect thread.

**Non-Goals:**
- Surface bodies.
- Bodies in an assembly.
- Scaling about a coordinate system; that waits for coordinate systems
  (queue item 39).
- Saving split bodies to files; `save_body_as_part` already does that.
- Move/copy by mates or constraints.

## Decisions

1. **Probe before building.** Some behaviour isn't in the help, so the
   first task is a short probe script, run with the user's OK. It answers:
   - which selection mark move/copy, delete and scale need on a body
     (`IBody2.Select2(append, ISelectData)`);
   - whether scale with no body selected scales every body;
   - what `PreSplitBody2` returns and what `PostSplitBody2` needs for
     `BodiesToMark`;
   - whether a combine "add" of bodies that don't touch succeeds;
   - the order of translation and rotation in `InsertMoveCopyBody2`.

   The answers go into this file before the adapter is written, as was done
   for the helix probe. Guessing would give silent no-ops, which is the
   failure the measurement exists to catch.
2. **A body is found by name each time,** case-insensitive, never cached:
   bodies are renamed by the very features we add. The lookup gives the
   `IBody2` dispatch and the list of names for refusals.
   - Alternative considered: persistent IDs (`GetPersistReference3`). That
     is more stable, but agents see names; names win.
3. **One measuring helper for bodies.** `_body_measured(op, names_in,
   build, rule)` reads the names, count and volume before; runs the build
   through `_handle_com_operation` (the settle pause, the connect thread);
   then reads them after. A `rule` per operation decides pass or fail. On
   fail it deletes the new feature, the way `_measured` does.
   - It is separate from `_measured` because the rules involve counts and
     boxes, not only the sign of the volume change.
   - The volume comes from summing `IBody2.GetMassProperties`, falling
     back to the part's mass properties, so a part with no body reads 0.
   - The tolerances are 0.1% for "unchanged" and 0.5% for scaling, which
     covers SolidWorks's tessellation error.
4. **Combine takes bodies, not a selection.** `InsertCombineFeature`
   receives the `IBody2` objects directly (the tool bodies as a
   `VT_DISPATCH` array), which avoids selection marks altogether.
5. **One tool per operation, not one `body_operation(kind=...)`.** Each
   operation has its own inputs, and agents choose better from a specific
   name and description.
6. **`delete_bodies` with `keep`** mirrors SolidWorks's own Delete/Keep Body
   feature, so one tool covers both.
7. **Layout follows the helix change:**
   - `adapters/solidworks/bodies.py` holds `SolidWorksBodiesMixin`;
   - `adapters/mock_bodies.py` holds `MockBodiesMixin`;
   - `tools/bodies.py` holds the inputs and the tool registration, with a
     new "bodies" toolset family;
   - `base.py` gains non-abstract methods that return "not implemented by
     this adapter", so other adapters keep working.
8. **The mock models bodies as boxes.** Each body is an axis-aligned box.
   - The volume of a subtract or common comes from box overlaps.
   - A split at a plane cuts the box in two.
   - A move shifts the box, a copy duplicates it, and a scale multiplies
     its size.

   This is enough to test every rule and refusal without SolidWorks.

## Risks / Trade-offs

- **[Selection marks are wrong, and the feature acts on nothing]** → the
  probe settles them, and the measurement fails the call rather than
  reporting success.
- **[SolidWorks renames bodies after a combine or split]** → the reply
  lists `bodies_after` by name, so the agent never guesses.
- **[A split by a sketch needs the sketch to cross the body fully]** → a
  failed split is caught: no new body, so the feature is deleted and the
  call fails, with a hint to draw the sketch across the whole body.
- **[`InsertMoveCopyBody2` translates along a selected edge when
  `TransDist` is set]** → we always pass x, y and z with `TransDist` 0 and
  select no edge.
- **[A large copy count is slow]** → `copies` is capped at 50.

## Migration Plan

None: six new tools, and nothing existing changes. They start beta and
move to stable after the live demo and the user's sign-off.

## Open Questions

None that change the specs. The probe answers (Decision 1) change only how
the adapter calls SolidWorks.
