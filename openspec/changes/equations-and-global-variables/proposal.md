## Why

Equations and global variables are how a SolidWorks part becomes
parametric: one value (`"Width" = 60mm`) drives several dimensions
(`"D1@Sketch1" = "Width" / 2`), so changing it resizes the whole part
consistently. The server has nothing for them today. An agent can set
dimensions one at a time (`set_dimension`), but it can't link them, so a
change to one size leaves the others stale, and a part an agent hands back
isn't parametric the way a SolidWorks user expects. Configurations (queue
item 13) give variants; equations give the relations inside each variant.
This is the base the macro-driven parametric features build on (the
user's direction, 2026-11-17).

## What Changes

- **`list_equations`**: every equation and global variable of the active
  part or assembly, in order, with its name, expression, kind (global
  variable, dimension, other) and current value.
- **`set_equation`**: adds a global variable or a dimension equation, or
  changes the expression of one that exists, in the configurations given
  (`all` by default, as in SolidWorks' Equations dialog; `this`, or a
  list). The model is solved and rebuilt, and the reply gives the new
  value. An expression SolidWorks refuses fails as `equation_refused` and
  nothing is changed.
- **`delete_equation`**: removes an equation or global variable by name.
  A dimension it drove keeps its last value.
- **`add_sketch_text`** (added for the wrench demo, 2026-11-18): text in
  the open sketch at a letter height, from a point or centred on a model
  point; cut or extruded, it debosses or embosses. A `$PRP:` link to a custom
  property that names a dimension makes the text follow that dimension,
  so the wrench's handle reads its own size after an equation changes it.
- Tool count 140 to 144.

## Capabilities

### New Capabilities

- `tools/equations`: reading, adding, changing and deleting equations and
  global variables.
- `tools/sketch-text`: text in a sketch at a height, from a point or
  centred on one, optionally showing a linked custom property.

### Modified Capabilities

None. (`tools/tool-naming` already allows `delete_`; its meaning in the
description standard gains "or equation".)

## Impact

- **COM, on the connect thread inside `_handle_com_operation`:**
  `IModelDoc2.GetEquationMgr()`; `IEquationMgr.GetCount`, `Equation`,
  `Value`, `GlobalVariable`, `Add3`, `SetEquationAndConfigurationOption`,
  `Delete`, `EvaluateAll`; `IModelDoc2.Parameter` to check a dimension
  name; `ForceRebuild3`. Argument lists checked against the installed
  2026 type library.
- **Code:** a new adapter mixin `adapters/solidworks/equations.py`; three
  adapter methods through `base.py`, `circuit_breaker.py`,
  `connection_pool.py`, `mock_adapter.py`; a new tool module
  `tools/equations.py`; `tool_hints.py`, `support_levels.py`,
  `toolsets.py`, an `equation_refused` rule in `error_classifier.py`.
- **Docs:** a catalog page, the agent skill's note on making a part
  parametric, the description standard's `delete_` meaning, CHANGELOG,
  progress bars.
- No issue is filed; this is queue item 29.
