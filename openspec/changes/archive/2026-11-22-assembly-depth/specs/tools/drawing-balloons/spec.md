## ADDED Requirements

### Requirement: Number a view's parts with balloons
`add_balloons` SHALL take a drawing `view_name` and a `layout` (`square`,
the default, `circle`, `top`, `bottom`, `left` or `right`). It SHALL add one
balloon per distinct part in the view, numbered as the BOM numbers them,
laid out around the view, and reply with the balloon count and their item
numbers.

#### Scenario: Three parts, three balloons
- **WHEN** an exploded view of an assembly of a base, four pins and two
  feet is ballooned
- **THEN** three balloons are added, one each for the base, the pin and the
  foot, matching the BOM's item numbers

#### Scenario: No such view
- **WHEN** `view_name` names no view on the sheet
- **THEN** it fails as `not_found`, listing the views
