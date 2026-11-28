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

   **Probe answers** (SolidWorks 2026 SP4, 2026-11-26, four scratch
   probes; every value below was read back from the bodies):

   - **Body order:** `GetBodies2(swSolidBody, False)` lists the bodies
     newest first, not in tree order. `list_bodies` gives them in the order
     SolidWorks lists them.
   - **Combine:** the tool bodies must be passed as a
     `VARIANT(VT_ARRAY | VT_DISPATCH)`; a plain list makes nothing.
     - Subtract takes `(15902, main, [tools])`. A 40 × 40 × 10 block minus
       a crossing cylinder gave the expected volume.
     - Add (15903) and common (15901) need **every** body in the array,
       the main body included; `(code, main, [main, *tools])` works. With
       only the others in the array they return None, and a Python `None`
       as `MainBody` is a type mismatch (a null `VT_DISPATCH` works too).
     - A 16,000 and a 4,000 mm³ block overlapping by 1,000 gave 19,000
       (add) and 1,000 (common).
     - The result is renamed `Combine1`.
   - **Split:** select the plane (`Select2(False, 0)`), then
     `PreSplitBody2()` returns the pieces (2 for a block across Right
     Plane). `PostSplitBody2(pieces, False, origins, paths, "")` then makes
     the split:
     - `origins` is a `VT_DISPATCH` array of nulls and `paths` a `VT_BSTR`
       array of empty strings, both as long as `pieces`;
     - with no arrays it makes nothing;
     - `ConsumeCut` true removes the pieces, so it is false;
     - the pieces are named `Split1[1]` and `Split1[2]`, 8,000 mm³ each.
   - **Move/copy:** the bodies are selected with mark 1 (mark 0 makes
     nothing).
     - Translation is in metres, rotation in radians about the model axes
       through the rotation point.
     - When both a rotation and a translation are given, SolidWorks applies
       only the rotation. `move_copy_body` therefore refuses both in one
       call; the agent moves twice.
     - A moved body is renamed `Body-Move/Copy1`; copies are
       `Body-Move/Copy1[1]` to `[n]`, copy n sitting n translations away.
   - **Delete/keep:** the bodies are selected with mark 0 (append for
     more). `InsertDeleteBody2(keep)` makes the `Body-Delete/Keep` feature.
     Keep two of three left exactly the two selected.
   - **Scale:** with no body selected `InsertScale` makes nothing. Selected
     with mark 0 or 1 (append for more), it scales them; we use 1.
     - Type 0 is the centroid and type 1 the origin.
     - The scaled bodies are renamed `Scale1`, or `Scale1[n]` for several.
     - Uniform ×2 gives 8× the volume, and 1 × 2 × 3 gives 6×.
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
