## ADDED Requirements

### Requirement: A view's own scale is applied and read back
`create_drawing_view` with a `scale` other than 1 SHALL give the new view its
own scale (no longer the sheet's) and reply with `scale_applied` true only
when the scale read back from the view matches.

#### Scenario: A half-scale top view
- **WHEN** a top view is placed with `scale` 0.5
- **THEN** the view is drawn at 1:2 while the sheet keeps its scale, and the
  reply says `scale_applied: true`

#### Scenario: A scale SolidWorks doesn't keep
- **WHEN** the view's scale reads back as something else
- **THEN** the reply says `scale_applied: false`

### Requirement: `view_type` names the view when `orientation` is left out
`create_drawing_view` with no `orientation` SHALL use `view_type` as the
orientation when it names one (`front`, `top`, `right`, `isometric`, ...),
and `front` otherwise.

#### Scenario: Only view_type
- **WHEN** a view is placed with `view_type` `isometric` and no
  `orientation`
- **THEN** it is an isometric view, not a front view
