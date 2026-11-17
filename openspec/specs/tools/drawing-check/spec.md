# tools/drawing-check Specification

## Purpose
`check_drawing` tells an agent whether the active drawing is complete
before it is exported, as findings it can act on with the other drawing
tools.
## Requirements
### Requirement: Findings for an incomplete drawing
`check_drawing` SHALL read the active drawing without changing it and
reply with `passed` and `findings`, each finding having `rule`, `severity`
(`error` or `warning`), `message` and, where it applies, `view`. The rules:

- `view_off_sheet` (error): a view's outline extends past the sheet;
- `view_not_dimensioned` (warning): a view, other than an isometric or
  detail view, has no dimensions;
- `title_block_field_empty` (warning): a title-block field the standard
  fills (title, drawn by, revision) is empty;
- `dangling_annotation` (error): an annotation has lost its reference;
- `bom_missing` (warning): the drawing's model is an assembly and the
  sheet has no BOM table.

`passed` SHALL be true when there are no `error` findings.

#### Scenario: A finished package
- **WHEN** a drawing from `generate_drawing_package` with model dimensions
  is checked
- **THEN** `passed` is true and `findings` is empty

#### Scenario: A view dragged off the sheet
- **WHEN** a view's outline crosses the sheet's edge
- **THEN** `passed` is false, and a `view_off_sheet` finding names the view

#### Scenario: An assembly drawing with no BOM
- **WHEN** an assembly's drawing has views but no BOM
- **THEN** a `bom_missing` warning is listed, and `passed` stays true

### Requirement: Only on a drawing
`check_drawing` SHALL fail with `wrong_document_type`, as every drawing
tool does, when the active document is not a drawing.

#### Scenario: A part is active
- **WHEN** a part is the active document
- **THEN** the call fails with `wrong_document_type` saying a drawing is needed

