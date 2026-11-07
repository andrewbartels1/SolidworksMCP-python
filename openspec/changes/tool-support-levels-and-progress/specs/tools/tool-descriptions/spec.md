## ADDED Requirements

### Requirement: A description states a level below stable

A `beta` or `experimental` tool's description SHALL open with its level and the reason, in one short sentence, before what the tool does.

#### Scenario: A beta tool
- **WHEN** an agent reads a `beta` tool's description
- **THEN** its first sentence starts "Beta:" and names the gap, e.g. "Beta: reads the material's name and library, not its properties."

#### Scenario: The level changes
- **WHEN** a tool's level changes in the table
- **THEN** the description check fails until the opening sentence matches the new level
