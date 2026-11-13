## MODIFIED Requirements

### Requirement: One support level per tool

Every registered tool SHALL have exactly one support level, `stable`, `beta`, `experimental`, `planned` or `deprecated`, recorded in one table, with a one-line reason for every level other than `stable`. A `deprecated` tool's reason SHALL name its replacement (or say there is none) and the version it was deprecated in.

#### Scenario: A new tool without a level
- **WHEN** a tool is registered that the table does not list
- **THEN** the support-level check fails and names the tool

#### Scenario: A listed tool that no longer exists
- **WHEN** the table lists a name that no registered tool has
- **THEN** the check fails and names it

#### Scenario: A deprecated tool without a replacement named
- **WHEN** a tool is `deprecated` and its entry names neither a registered replacement nor "no replacement"
- **THEN** the check fails and names the tool

### Requirement: Levels are consistent with the code

The check SHALL fail when a level contradicts what the code shows. A `planned` tool's reason SHALL name the queue item that builds it.

#### Scenario: Planned means not implemented
- **WHEN** a tool is `planned`
- **THEN** its description says "Not available yet", no tool outside `planned` says so, and its reason names a queue item

#### Scenario: Stable means checked live
- **WHEN** a tool is `stable`
- **THEN** at least one test under `tests/live/` calls it by name

#### Scenario: After the clean-up
- **WHEN** the levels are counted after this change
- **THEN** exactly seven tools are `planned`, all drawing tools, each naming queue item 12
