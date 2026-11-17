# tools/drawing-section-detail Specification

## Purpose
`create_section_view` and `create_detail_view` add the two derived views a
drawing package needs to show inside and small features.
## Requirements
### Requirement: A section view along a line
`create_section_view` SHALL take `view` (the parent view's name),
`line_start` and `line_end` (`[x, y]` in sheet millimetres, crossing the
view), `position` (`[x, y]` in sheet millimetres for the new view) and
`label` (default the next free letter). It SHALL add a section view cut
along that line, and reply with the new view's name, label and outline.

#### Scenario: A section through a plate with a hole
- **WHEN** a drawing has a front view of a plate with a hole, and
  `create_section_view` is called with a line across the hole's centre
- **THEN** `list_drawing_views` lists one more view, labelled `A`, and
  its outline is inside the sheet

#### Scenario: A line that misses the view
- **WHEN** the line lies wholly outside the parent view's outline
- **THEN** the call fails with `invalid_input` naming the view, and no view
  or sketch line is left behind

### Requirement: A detail view of a circle
`create_detail_view` SHALL take `view`, `center` (`[x, y]` in sheet
millimetres inside the view), `radius` in millimetres, `position`, `scale`
(for example `2:1`, default `2:1`) and `label`. It SHALL add a detail view
and reply with its name, label and scale.

#### Scenario: A detail of a corner
- **WHEN** `create_detail_view` is called with a circle on a corner of the
  front view and scale `3:1`
- **THEN** one more view exists, labelled, at scale 3:1

### Requirement: New views stay on the sheet
Both tools SHALL refuse a `position` that would put the new view's outline
off the sheet, before creating it, with `invalid_input` naming the sheet's
size.

#### Scenario: A position off the sheet
- **WHEN** `position` is beyond the sheet's right edge
- **THEN** the call fails with `invalid_input`, and no view is added

