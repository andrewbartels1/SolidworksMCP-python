## Purpose

Lets a caller auto-insert center marks for circular features in a drawing
view — a near-universal drawing-standards requirement, distinct from the
existing sketch-level `add_centerline`.

## ADDED Requirements

### Requirement: Center marks can be auto-inserted for a drawing view
The adapter SHALL expose `auto_center_marks`, which inserts a center mark
for every circular edge/hole visible in a named view on the active
drawing, and returns the count inserted (zero if none are found).

#### Scenario: View with multiple holes
- **WHEN** `auto_center_marks` is called on a view showing several
  circular holes
- **THEN** a center mark is inserted for each and the response reports
  the count

#### Scenario: View with no circular features
- **WHEN** `auto_center_marks` is called on a view with no circular edges
- **THEN** the response reports zero, not an error

### Requirement: auto_center_marks fails clearly for an unresolvable view
`auto_center_marks` SHALL return a failed `AdapterResult` — not raise —
when the given view name doesn't exist on the active drawing.

#### Scenario: View name does not exist
- **WHEN** `auto_center_marks` is called with a name matching no view on
  the active drawing
- **THEN** the response status indicates failure and nothing is inserted
