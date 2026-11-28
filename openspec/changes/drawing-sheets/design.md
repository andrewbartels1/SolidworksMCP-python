## Context

Motivation: see proposal.md.

**Probe (SolidWorks 2026 SP4, 2026-11-28; a new drawing, closed unsaved):**

- `IDrawingDoc.GetSheetNames()` gives the names in order; a new drawing has
  `Sheet1` (Letter, 279.4 x 215.9 mm, 1:1, third angle).
- `ISheet.GetProperties2()`: paper size code, template, scale numerator and
  denominator, first angle (1) or third (0), width and height (m), a flag.
  `IDrawingDoc.Sheet(name)` gives a sheet without activating it.
- `IDrawingDoc.NewSheet4(name, paperSize, template 12 (custom), scale1,
  scale2, firstAngle, formatPath, width m, height m, "Default", 0 x 6)`
  adds the sheet and makes it active; it returns False for a name in use.
- `IDrawingDoc.ActivateSheet(name)` returns False for a missing name.

## Goals / Non-Goals

**Goals:** see, add and choose sheets, by name, ignoring case.

**Non-Goals:** deleting, renaming or reordering sheets; per-sheet title
blocks (`update_title_block` writes the drawing's properties); the rest of
item 37 (callouts, auxiliary and break views, revision table).

## Decisions

1. **On the drawing pack.** `_pack_run` (drawing only, on the connect
   thread), `_pack_format_path`, `paper_for`, `parse_scale` and
   `PAPER_SIZES` are reused, so a format is found the way
   `update_sheet_format` finds it.
2. **Refused before SolidWorks.** A name in use and an unknown sheet are
   refused by the rules with the sheets listed, rather than by reading
   SolidWorks's False.
3. **Projection inherited.** A new sheet takes the active sheet's
   projection unless one is given, so a drawing stays consistent.
4. **Observed live:** `create_drawing_view` rescales the active sheet to
   fit its view, so a sheet added at 1:2 read 5:1 after an isometric view
   was placed on it. That is `create_drawing_view`'s behaviour; a question
   for the user.
