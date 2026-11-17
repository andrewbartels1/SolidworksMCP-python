## Purpose

`add_dimension` and `auto_dimension_view` put dimensions on drawing views,
by hand or automatically, so a drawing with views is a deliverable.

## ADDED Requirements

### Requirement: One dimension between picked entities
`add_dimension` SHALL take `dimension_type` (`horizontal`, `vertical`,
`aligned`, `radial`, `diameter` or `angular`), `entity1_point` and, for
the types that need two entities, `entity2_point` (`[x, y]` in sheet
millimetres on a view's edges or vertices), and `position` (`[x, y]` in
sheet millimetres for the text). It SHALL add one dimension and reply with
its name and measured value in millimetres (degrees for angular).

#### Scenario: A plate's width
- **WHEN** a front view of a 60 mm wide plate is on the sheet and
  `add_dimension` is called with `horizontal` and points on its left and
  right edges
- **THEN** one dimension is added and its value is 60 within 0.01 mm

#### Scenario: A hole's diameter
- **WHEN** `add_dimension` is called with `diameter` and a point on a
  Ø6 mm hole's edge
- **THEN** the value is 6 within 0.01 mm

#### Scenario: A point on no entity
- **WHEN** `entity1_point` is on empty sheet
- **THEN** the call fails with `invalid_input` naming the point, and no
  dimension is added

### Requirement: Auto-dimension one view
`auto_dimension_view` SHALL take `view`, `scheme` (`baseline` or `chain`,
default `baseline`) and apply SolidWorks' auto-dimension to that view's
edges, horizontally and vertically, replying with the number of
dimensions added.

#### Scenario: A plate's front view
- **WHEN** `auto_dimension_view` is called on a plate's front view
- **THEN** the reply's `added` is at least 2, and the view's dimension
  count rises by that number

#### Scenario: A view that doesn't exist
- **WHEN** `view` names no view on the sheet
- **THEN** the call fails with `not_found` listing the views, as the other
  drawing tools do for an unknown view
