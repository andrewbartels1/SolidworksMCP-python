## Purpose

When `pattern_circular` and `mirror_feature` count as having worked, for
features that add material and features that remove it.

## ADDED Requirements

### Requirement: A pattern or mirror succeeds when the volume changes

`pattern_circular` and `mirror_feature` SHALL succeed when the part's volume
changes, up or down, and SHALL fail when it doesn't change. The reply SHALL
include the volume before and after.

#### Scenario: A ring of holes
- **WHEN** an agent patterns a Ø6 mm through-hole in a 10 mm plate 6 times around an axis, with every instance on the plate
- **THEN** the call succeeds and the volume falls by 5 × π·3²·10 = 1,413.7 mm³ within 0.1 %

#### Scenario: A mirrored cut
- **WHEN** an agent mirrors a cut about a plane, and the mirrored cut lands on the body
- **THEN** the call succeeds and the volume falls by the cut's volume

#### Scenario: Nothing patterned
- **WHEN** a pattern's instances all land off the body, so the volume is unchanged
- **THEN** the call fails and says the pattern produced no geometry
