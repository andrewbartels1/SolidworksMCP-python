## ADDED Requirements

### Requirement: One support level per tool

Every registered tool SHALL have exactly one support level, `stable`, `beta`, `experimental` or `planned`, recorded in one table, with a one-line reason for every level below `stable`.

#### Scenario: A new tool without a level
- **WHEN** a tool is registered that the table does not list
- **THEN** the support-level check fails and names the tool

#### Scenario: A listed tool that no longer exists
- **WHEN** the table lists a name that no registered tool has
- **THEN** the check fails and names it

### Requirement: Levels are consistent with the code

The check SHALL fail when a level contradicts what the code shows.

#### Scenario: Planned means not implemented
- **WHEN** a tool is `planned`
- **THEN** its description says "Not available yet", and no tool outside `planned` says so

#### Scenario: Stable means checked live
- **WHEN** a tool is `stable`
- **THEN** at least one test under `tests/live/` calls it by name

### Requirement: The level is visible to clients

A tool's level SHALL be shown in its tags and, below `stable`, in its results.

#### Scenario: Tags
- **WHEN** a client lists the tools
- **THEN** each tool's tags include `level:<level>` beside its family tag

#### Scenario: A beta tool succeeds
- **WHEN** a `beta` or `experimental` tool returns `status: success`
- **THEN** the result also carries `warning`, a sentence giving the level and its reason, and every other key is unchanged

#### Scenario: A stable tool succeeds
- **WHEN** a `stable` tool returns `status: success`
- **THEN** the result has no `warning` key
