# setup/toolsets Specification

## Purpose
A user chooses which tool families their client sees, so a client pays
only for the tools its work needs.
## Requirements
### Requirement: Toolsets choose the visible families
The server SHALL read `SOLIDWORKS_MCP_TOOLSETS`, a comma-separated list of
`core`, `drawing`, `automation`, `vba`, `docs` and `all`. Only tools whose
family belongs to a listed toolset SHALL appear in `tools/list` and be
callable. Unset or `all` SHALL show every tool.

#### Scenario: Core only
- **WHEN** the server starts with `SOLIDWORKS_MCP_TOOLSETS=core`
- **THEN** `tools/list` holds `create_extrusion` and `open_model`, and no
  `generate_vba_*`, drawing or API-help tool

#### Scenario: Core and drawing
- **WHEN** the setting is `core,drawing`
- **THEN** `create_drawing_view` is listed too, and the VBA generators are
  not

#### Scenario: Default
- **WHEN** the setting is unset
- **THEN** `tools/list` is the same as before this change

### Requirement: A bad toolset name stops the server with a clear error
The server SHALL refuse to start when `SOLIDWORKS_MCP_TOOLSETS` names an
unknown toolset, and the error SHALL list the valid names.

#### Scenario: A typo
- **WHEN** the setting is `core,drawings`
- **THEN** the server exits at start with an error naming `drawings` and
  the valid toolsets

### Requirement: Every family is in exactly one toolset
Each tool family SHALL belong to exactly one toolset, and a check SHALL
fail on a family that belongs to none or more than one.

#### Scenario: A new family
- **WHEN** a new tool module adds a family no toolset lists
- **THEN** the check fails and names the family

