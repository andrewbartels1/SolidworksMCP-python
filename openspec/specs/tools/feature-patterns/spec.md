# tools/feature-patterns Specification

## Purpose
When `pattern_circular` and `mirror_feature` count as having worked, for
features that add material and features that remove it.
## Requirements
### Requirement: A pattern or mirror succeeds when the volume changes

`pattern_circular`, `pattern_linear` and `mirror_feature` SHALL succeed when the part's volume
changes, up or down, and SHALL fail when it doesn't change. The reply SHALL
include the volume before and after.

#### Scenario: A ring of holes
- **WHEN** an agent patterns a Ø6 mm through-hole in a 10 mm plate 6 times around an axis, with every instance on the plate
- **THEN** the call succeeds and the volume falls by 5 × π·3²·10 = 1,413.7 mm³ within 0.1 %

#### Scenario: A row of holes
- **WHEN** an agent patterns a Ø6 mm through-hole in a 10 mm plate 4 times at 15 mm along a straight edge of the plate
- **THEN** the call succeeds and the volume falls by 3 × π·3²·10 = 848.2 mm³ within 0.1 %

#### Scenario: A mirrored cut
- **WHEN** an agent mirrors a cut about a plane, and the mirrored cut lands on the body
- **THEN** the call succeeds and the volume falls by the cut's volume

#### Scenario: Nothing patterned
- **WHEN** a pattern's instances all land off the body, so the volume is unchanged
- **THEN** the call fails and says the pattern produced no geometry

### Requirement: A linear pattern along one or two directions
`pattern_linear` SHALL take `features` (at least one name), `direction_1`
(an edge picked by a point, or an axis name), `count_1` (at least 2) and
`spacing_1` in millimetres, and optionally `direction_2`, `count_2` and
`spacing_2` for a grid, plus `reverse_1` and `reverse_2`.

#### Scenario: A 3 × 2 grid
- **WHEN** a hole is patterned 3 times at 15 mm along one edge and 2 times at 20 mm along the other
- **THEN** six holes exist in all and the volume falls by five holes' volume

