## ADDED Requirements

### Requirement: The drawing's sheets
`list_sheets` SHALL list the active drawing's sheets in order, each with
`name`, `active`, `paper_mm` (`[width, height]`), `scale` (`"1:2"`) and
`projection` (`first` or `third`), read without changing the active sheet,
with `count` and `active`. It SHALL fail when the active document is not a
drawing.

#### Scenario: A new drawing
- **WHEN** it is called on a new drawing
- **THEN** it lists `Sheet1`, active, with its paper size and scale

### Requirement: A new sheet
`add_sheet` SHALL add a sheet named `name` with the format `sheet_format`
(a name found in SolidWorks's sheet format folders or a `.slddrt` path),
the paper size (from the format's name unless given), `scale` and
`projection` (the active sheet's unless given), make it active, and reply
with `added`, `sheet_format` and the listing after. A name in use (ignoring
case), an unknown format, a bad scale or projection SHALL fail with
`invalid_input`, changing nothing.

#### Scenario: A details sheet
- **WHEN** it is called with `name` "Details", `sheet_format` "a2 - iso"
  and `scale` "1:2"
- **THEN** the listing has Details, active, 594 x 420 mm, at 1:2

#### Scenario: A name in use
- **WHEN** it is called with `name` "sheet1" on a drawing with Sheet1
- **THEN** it fails with `invalid_input`, listing the sheets

### Requirement: The active sheet
`activate_sheet` SHALL make the sheet named `name` (ignoring case) the
active one and reply with the listing after. An unknown name SHALL fail
with `invalid_input`, listing the sheets.

#### Scenario: Back to the first sheet
- **WHEN** it is called with "SHEET1" while Details is active
- **THEN** Sheet1 is active
