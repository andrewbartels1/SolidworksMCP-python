# tools/tool-requirements Specification

## Purpose
TBD - created by archiving change tool-requirements. Update Purpose after archive.
## Requirements
### Requirement: One requirement per tool

Every registered tool SHALL have exactly one requirement, `nothing`,
`installed` or `running`, recorded in one table that lists only the tools
that are not `running`. The README and docs SHALL state that no tool needs
a licence above the one that runs SolidWorks, and name the release it was
checked on.

#### Scenario: A listed tool that no longer exists
- **WHEN** the table lists a name that no registered tool has
- **THEN** the check fails and names it

#### Scenario: An installed tool says so
- **WHEN** a tool is `installed`
- **THEN** its description says SolidWorks need not be running

### Requirement: The requirement is visible to clients

A tool's requirement SHALL be in its tags as `needs:<requirement>`.

#### Scenario: Tags
- **WHEN** a client lists the tools
- **THEN** each tool has exactly one `needs:` tag, and `lookup_api_method` has `needs:installed`

### Requirement: The docs list the tools that don't need SolidWorks running

The tools overview SHALL list every `nothing` and `installed` tool by name
under its requirement, and the check SHALL fail when the list and the
table differ.

#### Scenario: A tool added to the table but not the docs
- **WHEN** the table and the overview's list differ
- **THEN** the check fails and names the difference

