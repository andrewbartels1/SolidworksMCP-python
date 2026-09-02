## Purpose

Lets a caller read a logged tool call's rendered Python line straight from
`ToolCallRecord`, instead of re-running the SolidWorks-as-Code exporter
over an entire session to see what one call would emit.

## ADDED Requirements

### Requirement: Tool call records carry their rendered script line
Each `ToolCallRecord` written after this change SHALL carry a
`script_line` field: that call's rendered Python, computed at write time
from its tool name and input/output payloads.

#### Scenario: New tool call is recorded with its script line
- **WHEN** a tool call is executed and its record is inserted
- **THEN** the record's `script_line` contains that call's rendered
  Python

### Requirement: Existing databases gain the column without manual action
Opening a database created before this change SHALL NOT fail or require
manual intervention: the `script_line` column SHALL be added
automatically the first time the database is opened after upgrading.

#### Scenario: Opening a pre-existing database
- **WHEN** the database is initialized against a file created before this
  change (no `script_line` column)
- **THEN** the column is added automatically and subsequent inserts and
  queries succeed without error

### Requirement: Session export handles both new and legacy records
Session export SHALL join stored `script_line` values where present, and
fall back to on-demand rendering for legacy records (written before this
change, `script_line` is `None`) — producing an identical script either
way.

#### Scenario: Exporting a session with legacy records
- **WHEN** a session is exported with pre-change records lacking
  `script_line`
- **THEN** those lines are rendered on demand and the result matches a
  full re-render of the session

#### Scenario: Exporting a session with only new records
- **WHEN** a session is exported with only post-change records
- **THEN** the script is assembled from their stored `script_line` values
