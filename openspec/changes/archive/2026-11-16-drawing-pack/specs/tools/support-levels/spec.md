## MODIFIED Requirements

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
- **THEN** no tool is `planned`: the seven drawing tools the honest tool list left planned are built
