## Context

SolidWorks keeps a document's equations in one ordered list
(`IModelDoc2.GetEquationMgr()`), each a text like `"Width" = 60mm` or
`"D1@Sketch1" = "Width" / 2`. Global variables are equations whose left
side is a plain name; dimension equations name a dimension the way
`list_model_dimensions` reports `full_name` (`D1@Sketch1`). The 2026 type
library's `IEquationMgr` has `Add3(Index, Equation, Solve,
WhichConfigurations, ConfigNames)`, `SetEquationAndConfigurationOption(
Index, Equation, WhichConfigurations, ConfigNames)`, `Delete(Index)`,
`GetCount()`, `EvaluateAll()`, and the indexed properties `Equation`,
`Value` and `GlobalVariable`.

## Goals / Non-Goals

**Goals:** read, add, change and delete equations and global variables,
in chosen configurations, with the solved values in the reply.

**Non-Goals:** linking equations to an external file
(`LinkToFile`, `UpdateValuesFromExternalEquationFile`); suppression
equations' own tool; equation folders and solve order
(`AutomaticSolveOrder` stays as the document has it).

## Decisions

1. **Name and expression, not raw text.** The agent gives `name` and
   `expression`; the server writes `"<name>" = <expression>`. Getting the
   quotes right is the commonest mistake in hand-written equations, and a
   `name` lets the tool find an existing equation to change. `name` may
   not contain `"`, `=` or a line break; `expression` may not be empty or
   contain a line break.
2. **Add or change in one tool, `set_equation`.** "Set Width to 60" is
   the same request whether `Width` exists or not, and the verb list's
   `set_` is "changes one value". The reply says `added` or `changed`.
3. **Finding an equation.** Walk `Equation(i)` for `i` in
   `0..GetCount()-1` and take the text between the first pair of quotes
   as its name; compare without case, as SolidWorks does.
4. **Checking.** A dimension name is checked with
   `IModelDoc2.Parameter(name)` before anything is written. After
   `Add3`/`SetEquationAndConfigurationOption`, the stored text is read
   back from `Equation(index)`: `Add3` returning -1, or the stored text
   not being the one written, is a refusal. A refused change restores the
   previous text, so nothing is left half-done. The return value of
   `SetEquationAndConfigurationOption` is not relied on (its meaning
   isn't documented in the type library); the read-back is.
5. **Configurations default to `all`**, as SolidWorks' Equations dialog
   does, unlike `set_dimension` (`this`, as SolidWorks' dimension
   dialog). The scope reuses `configuration_scope` from
   `adapters/solidworks/configurations.py`, so names are checked the same
   way and the same `swInConfigurationOpts_e` values go to COM.
6. **Solve and rebuild.** `EvaluateAll()` then `ForceRebuild3(False)`
   after every add, change or delete; the reply's `value` is read after
   that. `Value(i)` is expected in the document's units (60 for `60mm` in
   an MMGS part); the live test confirms it, and the tool descriptions say
   so.
7. **Refusal type.** A new classifier rule, `equation_refused`, appended
   to the rule table, matches the adapter's "SolidWorks refused the
   equation" message; its hint says to check the names in quotes with
   `list_equations` and `list_model_dimensions`.
8. **Where the code lives.** A new tool module `tools/equations.py` and
   adapter mixin `adapters/solidworks/equations.py`, mirrored by
   `tests/solidworks_mcp/tools/test_equations.py` and
   `tests/solidworks_mcp/adapters/solidworks/test_equations.py`. The tools
   join the `modeling` toolset.
9. **Mock adapter.** Keeps a list of equations; `value` is a number when
   the expression is a number (with an optional `mm`, `in` or `deg`) or a
   quoted global variable that has one, otherwise null. An expression
   naming a global variable that doesn't exist is refused, so the
   `equation_refused` path is exercised without SolidWorks.

## Risks / Trade-offs

- **Units of `Value`** may turn out to be SI (0.06 for 60 mm). The live
  test checks it first; if so, the reply converts dimension values to mm
  and degrees as the other tools do, and the design is updated.
- **`Add3` on an assembly** writes the equation on the assembly; an
  equation driving a part's dimension inside it needs the
  `D1@Sketch1@Part1<1>` form. Out of scope for the live check; the
  description says the dimension must be the active document's own.

## Migration Plan

New tools only; nothing existing changes.
