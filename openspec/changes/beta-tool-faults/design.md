## Context

- `support_levels.py` rates 23 tools `beta`, each with a one-line reason. The
  same faults sit in the skill's known-faults table
  (`skills/solidworks-mcp/references/errors-and-limits.md`) and in the
  queue's "Small faults" list.
- Every input model subclasses `CompatInput`, which has `extra="allow"`. Taking
  a field off a schema today means a client that still sends it is ignored
  silently. That is the same fault this change fixes.
- `create_cut_extrude` already resolves its sketch strictly. It matches
  `sketch_name` against the live tree without regard to case, falls back to
  `_last_sketch_name` only when that name exists in the tree, never guesses,
  and selects the sketch with `SelectByID2` before the feature call
  (`adapters/solidworks/features.py`, around line 1336). `create_extrusion`
  and `create_revolve` skip all of this and rely on whatever is selected.
- The pattern and mirror adapters measure the volume before and after, which
  is right, because SolidWorks returns a Feature even when it built nothing.
  But they demand growth, so a cut can never pass.
- The real `delete_feature` returns `features_removed`, a count. The tool reads
  `removed_features`, a list that only the mock returns.
- `get_mass_properties` returns moments of inertia in kg·m², because SolidWorks
  works in SI. The tool labels them kg·mm².

## Goals / Non-Goals

**Goals:**

- All 23 tools move to `stable`, each called by a live test that proves its
  fix.
- No schema field is ignored. Each one is either honoured or refused with a
  pointer to the right tool or input.
- The skill's known-faults table loses every row this change fixes.

**Non-Goals:**

- Merging duplicate tools. `add_drawing_view` and `create_drawing_view`, and
  `get_mass_properties` and `calculate_mass_properties`, stay separate here;
  #174 decides which name survives.
- Material properties beyond density. Those are the planned tool
  `get_material_properties` (queue item 10).
- `add_mate` with edges or vertices. That is a new capability, not a beta
  fault.
- Export options such as STL resolution or PDF sheets. If they're wanted
  later, they come back as a typed input per format, not a free-form dict.

## Decisions

### 1. Honour or remove: the rule

An input is **honoured** when SolidWorks supports it in a call or two and no
other tool does the job. It is **removed** when another tool does the job
better, or when honouring it would turn the tool into a different one. For
example, `create_drawing` with `model_path` would become
`generate_drawing_package`.

| Tool | Input | Decision | How |
| --- | --- | --- | --- |
| `create_extrusion` | `sketch_name` | honour | Shared sketch resolver (decision 3) |
| `create_extrusion` | `direction` | remove | Duplicates `end_condition` |
| `create_revolve` | `sketch_name`, `axis_entity` | honour | Shared resolver; axis selected with mark 4 (decision 4) |
| `create_revolve` | `direction` | remove | Duplicates `both_directions`; reply stops echoing it |
| `create_sketch` | `sketch_name` | honour | Rename after `InsertSketch` (decision 5) |
| `create_part` | `material` | honour | The adapter's `set_material` after the part opens |
| `create_assembly` | `components` | remove | `insert_component` places each part |
| `create_drawing` | `model_path`, `sheet_format` | remove | `create_drawing_view`, `generate_drawing_package` |
| `create_technical_drawing` | `template`, `sheet_size`, `title`, `output_path` | remove | It places views on the active drawing; `generate_drawing_package` makes a whole drawing |
| `check_interference` | `include_hidden` | honour | Pass `ignore_hidden = not include_hidden` |
| `check_interference` | `tolerance`, `check_all_components` | remove | Unused; SolidWorks' check has no tolerance |
| `save_as` | `overwrite` | honour | The tool checks the path before the adapter call |
| `save_file` | `force_save` | remove | SolidWorks saves either way |
| `export_*` (5) | `options` | remove | The extension sets the format |
| `execute_macro` | `repeat_count`, `pause_between_runs` | honour | A loop in the tool (decision 7) |
| `calculate_mass_properties` | its 4 inputs | remove | It always measures the active model |
| `add_drawing_view` | `operation` other than `add` | refuse | It only adds views |

Any other unused `execute_macro` field found during the work (`execution_mode`,
`pause_on_error`, `log_execution`) gets the same treatment by the same rule.
The decision is recorded in tasks.md.

### 2. Refusing removed inputs: one helper

`input_compat.py` gains `REMOVED_INPUTS: dict[tuple[str, str], str]`, mapping
(model class, field) to a pointer sentence, and
`reject_removed_inputs(model)`. `normalize_input` calls the helper after
validation. It raises `InvalidInputError` when any removed field is among the
model's extras (`model.model_extra`). So a removed field leaves the schema
(clients stop seeing it), and a stale client still gets a clear
`invalid_input`. No tool gains a `try/except`; the error boundary formats the
error.

Not chosen:

- **Keeping the fields with `deprecated=True`.** The schema would still
  advertise them, and agents read schemas.
- **Switching `CompatInput` to `extra="forbid"`.** That would break the
  aliases it exists for.

### 3. One sketch resolver for extrude, revolve and cut

Lift the resolution block out of the cut-extrude implementation into
`_resolve_profile_sketch(adapter, sketch_name) -> str`. It:

1. matches `sketch_name` against the tree without regard to case;
2. if `sketch_name` is empty, falls back to `_last_sketch_name`, but only if
   that name is in the tree;
3. otherwise raises an error listing the available sketches;
4. selects the result with `SelectByID2(..., "SKETCH", ..., _null_callout(), 0)`.

The extrude, revolve and cut implementations all call it inside their
`_handle_com_operation` closures. `ExtrusionParameters` and
`RevolveParameters` gain `sketch_name: str | None`. The cut's behaviour and
messages are unchanged, so its existing tests are the regression check.

### 4. The revolve axis

When `axis_entity` is given, the resolver selects the profile with mark 0 and
appends the axis with `SelectByID2(axis_entity, "AXIS", ..., append=True,
mark=4)`. Without it, the sketch's centreline is used as today. A name that
isn't an axis in the tree fails before the feature call. `axis_entity` becomes
optional in `CreateRevolveInput`. That is not breaking: it was required, and
every existing caller passes a value, which is now either used or rejected
with a clear reason. A centreline name such as "Line1" can't be selected by
`SelectByID2` reliably. So any value that isn't a reference axis fails with a
hint: draw the axis with `add_centerline` and leave `axis_entity` out.

### 5. Naming a new sketch

After `InsertSketch` returns the active sketch, read its feature
(`ISketch` → `IFeature`, the cast the adapter already makes in `exit_sketch`)
and set `Name`. If the setter is refused (the name is taken, or SolidWorks
won't rename a sketch in edit mode), keep the original name and return a
`warning`. The live test settles which happens. If renaming during edit is
refused, the rename moves to `exit_sketch`, and `create_sketch` remembers the
wanted name. The spec allows either route, because both give the name in the
tree.

### 6. Pattern and mirror: any volume change counts

Replace the growth test with `abs(after - before) > before * tolerance`.
Pattern keeps its 0.01 % tolerance and mirror its 0.1 %. The error text loses
the "did not grow" wording. The reply already carries `volume_before` and
`volume_after`, and gains `volume_change`, which is negative for a cut.

### 7. Repeating a macro

The tool loops `repeat_count` times and calls `adapter.execute_macro` each
time. It waits `asyncio.sleep(pause_between_runs)` between runs, so it stays on
the event-loop thread, as the COM rule requires. It stops at the first failure.
The reply gains `runs_completed`. A failure after some successes raises
`ToolOperationError` with the count. `repeat_count` gets `ge=1, le=100`, so a
typo can't hang SolidWorks for hours.

### 8. Units and the rest

- **Mass properties:** the tool multiplies the moments and products of inertia
  by 1e6 (kg·m² → kg·mm²). The `MassProperties` dataclass stays SI, and
  `verify_model` doesn't read inertia. The label says kg·mm², and the
  description stops warning about it.
- **`get_material`:** density comes from `IPartDoc.GetMaterialPropertyValues2`
  where it's available. Otherwise it comes from the material database entry
  the adapter already finds. If neither is readable, it's `null`, never a guess.
- **`delete_feature`:** the adapter lists feature names before and after
  (it already counts both) and returns `removed_features` as the names that
  went, in tree order. The mock returns the same shape.
- **`save_as`:** `Path(file_path).exists() and not overwrite` raises
  `InvalidInputError` before any COM call.

### 9. Live tests and sign-off

`tests/live/test_live_sw_beta_tools.py` has one test per tool, each printing
`[evidence]` lines. They run in five batches, each with the user's permission
and at the usual pace:

1. sketch and feature inputs (extrude, revolve, sketch name, part material)
2. patterns, mirror and delete
3. mass properties, interference and material density
4. files (`save_as` overwrite, `save_file`, the five exports, macro repeats)
5. drawings (`create_drawing`, `create_technical_drawing`, `add_drawing_view`)
   and the tutorial

A batch that fails is fixed and run again before the next one starts. A tool
is promoted only after its batch passes.

## Risks / Trade-offs

- [**Clients sending a removed input now get an error.**] The error names the
  replacement, and the CHANGELOG lists every removed field. The fields did
  nothing before, so no result changes, only the reply.
- [**Renaming a sketch in edit mode may be refused.**] Decision 5's fallback
  covers it. The live test runs first in batch 1, so the route is settled
  early.
- [**`IgnoreHiddenBodies` may cover hidden bodies, not hidden components.**]
  Batch 3 tests a hidden component. If SolidWorks still reports it, the fix
  moves to the adapter's components filter, and the requirement doesn't change.
- [**Changing the moments of inertia by 1e6 changes numbers clients may have
  saved.**] The old numbers were labelled wrong, so any saved value was already
  misread. The CHANGELOG says so.
- [**Shared sketch resolution changes cut-extrude's code path.**] The cut's
  unit tests and its live tests run unchanged in batch 1.

## Migration Plan

Removed fields are listed in the CHANGELOG under **Changed**, each with its
replacement. No data migration. Rollback is reverting the PR.

## Open Questions

None. Decisions 4 and 5 each have a fallback that the live tests settle.
