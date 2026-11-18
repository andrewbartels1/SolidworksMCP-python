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
4. **The COM calls, as measured on SolidWorks 2026** (live probes,
   2026-11-17/18). Every call that takes an array of configuration names
   returns -1 from Python, whatever the array's form (`Add3`,
   `SetEquationAndConfigurationOption`, `ISetEquationAndConfiguration
   Option`), so none is given names:
   - **add:** `Add2(-1, text, True)`, which adds in every configuration
     and returns the new index, or -1 when refused;
   - **change in every configuration:** write the `Equation(i)` property
     (an `IDispatch` property put; pywin32's late binding can't assign an
     indexed property). `SetEquationAndConfigurationOption(i, text, 2,
     None)` worked on a two-equation part but returned -1 on the wrench's
     19, even for the same text;
   - **this configuration:** `SetEquationAndConfigurationOption(i, text,
     1, None)` with the configuration active; it returns 0;
   - **named configurations:** each made active in turn and set as "this
     configuration", then the one that was active is shown again,
     whatever happens; the reply's `values` gives each one's solved value.

   A dimension name is checked with `IModelDoc2.Parameter(name)` before
   anything is written. A refusal is the call's -1, `Status` going to -1,
   or the stored text not reading back as written (ignoring spaces and
   case: SolidWorks respaces it). A refused add is deleted again; a refused
   change restores the previous text, so nothing is left half-done.
   `EvaluateAll`'s return value isn't used: it returned -1 on a part that
   solved.
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

- **Units of `Value`**: confirmed live as the document's units (`19.0`
  for `19mm` in an MMGS part), so the reply passes it through.
- **`Add3` on an assembly** writes the equation on the assembly; an
  equation driving a part's dimension inside it needs the
  `D1@Sketch1@Part1<1>` form. Out of scope for the live check; the
  description says the dimension must be the active document's own.

## The wrench demo, and two tool fixes it needed

The live demo (`tests/live/test_live_sw_equations_wrench.py`, on the
demos page and in the README) builds a 13 mm combination wrench and drives
all twelve of its sizing dimensions from one global variable. Every size
grows from the centre line, so the wrench keeps its shape at any size.
Building it found two gaps, fixed here:

- **`create_cut_extrude` with `both_directions` on a Blind cut** cut one
  way only (the flag was read only with `ThroughAll`). It is now a
  mid-plane cut, `depth` in total, as `create_extrusion` already did.
- **Polygons couldn't be sized by a dimension or turned.**
  `add_sketch_dimension` with `diameter` on a polygon's `id` now
  dimensions the circle `CreatePolygon` draws inside it (across flats
  for a hexagon), and `add_polygon` takes an `angle` (the first corner's
  turn from +x), so two hexagons 30° apart make a 12-point opening.
  SolidWorks wouldn't linear-pattern a circular pattern of one hexagon,
  which is why the second is drawn turned.
- **Ellipses couldn't be turned or sized by a dimension.** On the user's
  reference wrench the jaw's bottom is a shallow curve that meets both
  jaw walls. Here that is an ellipse cut at the head's centre: its major
  axis is Size long across the jaw (turned 15° with it), its minor axis
  0.2 x Size. `add_ellipse` now takes an `angle` (the major axis's turn
  from +x), and `add_sketch_dimension` takes `major_axis` and
  `minor_axis` on an ellipse's `id`. Each is a dimension from the centre
  to that axis's end point, so it holds half the axis (an ellipse has no
  point at the other end to dimension the whole axis to); `value` is the
  whole axis, as `add_ellipse` takes it.

## Text on the wrench's handle: `add_sketch_text`

The user asked for "solidworksmcp-python" and the wrench's size debossed
on both faces of the handle, so the size visibly changes with the
equations. Probed on SolidWorks 2026 (2026-11-18, scratch parts):

- `IModelDoc2.InsertSketchText(x, y, z, text, alignment, flip,
  horizontal_mirror, width_factor, space_between_chars)` adds text to the
  open sketch. `space_between_chars` 0 stacked every letter on the first;
  100 (per cent, as `width_factor`) spaces them normally.
- A line selected first did NOT lay the text along it (the user's
  suggestion, the usual way in the SolidWorks UI): the text stayed at the
  point given, and moving the line by its dimension left the text where it
  was. Centre alignment (2) didn't centre it either, and a mirrored text
  (`horizontal_mirror` 1) cut nothing. The tool uses none of them.
- The height is `ISketchText.GetTextFormat()`, `CharHeight` (metres),
  `SetTextFormat(False, format)`; the default was 3.5 mm.
- Centring works by measuring: `ISketchText.GetEdges2()` gives the
  letters' edges (model space; `GetCurveParams3` start and end points
  bound them), their middle is mapped into the sketch
  (`ModelToSketchTransform`), and `SetCoordinates` moves the text by the
  difference to the target point. On a 120 mm bar the text came out in
  its middle, on the top face and on the underside.
- Text in a sketch opened on the underside face (`face_point`) reads
  correctly from below; on a plane offset below the part it reads
  mirrored.
- Text `solidworksmcp-python $PRP:"WrenchSize" mm`, with the file property
  `WrenchSize` = `"D1@Boss-Extrude1"`, read `... 4.00 mm`, and `... 6.00
  mm` after the dimension changed: the text follows the dimension.

The tool is `add_sketch_text(text, x, y, height, center_at)`.

A sketch text's position can't be driven by an equation, but the
wrench's handle middle moves with Size (x = 6.51 x Size). So the
lettering is cut, centred, into the faces of a spare block off the open
end (x = -190 mm, as thick as the handle), the two cuts are moved onto the
handle by a linear pattern whose spacing is `"Size" * 6.51 + 190mm`, and
the block is cut away, as the box end's pattern seed is. `WrenchSize` is
linked to a dimension the equations set to Size.

## Migration Plan

New tools; `add_polygon`'s and `add_ellipse`'s `angle` default to 0, so
existing calls are unchanged. A Blind cut with `both_directions` now cuts both ways, as its
name and the extrusion tool always said.
