## Purpose

`update_title_block` and `update_sheet_format` change an existing drawing's
title block and sheet, so an agent can revise a drawing without
regenerating it.

## ADDED Requirements

### Requirement: Title-block fields on an existing drawing
`update_title_block` SHALL take any of `title`, `drawing_number`,
`drawn_by`, `drawn_date`, `revision` and `company` (at least one), write
each to the property the sheet format reads (the same mapping
`generate_drawing_package` uses), rebuild, and reply with the fields it
set. Fields not given SHALL keep their values.

#### Scenario: A new revision
- **WHEN** a drawing made by `generate_drawing_package` is active and
  `update_title_block` is called with `revision` `B`
- **THEN** the title block shows `B`, and the title and drawn-by fields are
  unchanged

#### Scenario: No fields
- **WHEN** `update_title_block` is called with no fields
- **THEN** the call fails with `invalid_input` listing the fields

### Requirement: A different sheet format, keeping the views
`update_sheet_format` SHALL take `sheet_format` (a format name found by
`find_sheet_format`, or a path to a `.slddrt` file) and optionally
`paper_size`. It SHALL change the active sheet's format, keep every view,
and reply with the format's path and the sheet's size.

#### Scenario: From A3 to A2
- **WHEN** the active sheet uses `a3 - iso` and `update_sheet_format` is
  called with `a2 - iso`
- **THEN** the sheet is A2, `list_drawing_views` lists the same views, and
  the title block's fields still show their values

#### Scenario: A format that doesn't exist
- **WHEN** `sheet_format` names no format SolidWorks can find
- **THEN** the call fails with `invalid_input` naming where it looked,
  and the sheet is unchanged
