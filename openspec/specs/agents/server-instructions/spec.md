# agents/server-instructions Specification

## Purpose
TBD - created by archiving change agent-skill-and-instructions. Update Purpose after archive.
## Requirements
### Requirement: The server sends short usage instructions at connection

The server SHALL send an `instructions` text in its MCP initialize response.
It SHALL be at most 1500 characters and SHALL say:

- to call `get_model_info` (or `list_open_documents`) first, to see what is
  open;
- the build order: `create_sketch`, draw, `exit_sketch`, then the feature;
- that inputs are millimetres and degrees unless a field says otherwise;
- to finish a build with `verify_model`, since a tool's success does not
  prove the geometry;
- that tools whose description starts "Not available yet" return
  `not_supported`;
- where the full guidance is: the `skill://solidworks-mcp/SKILL.md` resource.

Every tool it names SHALL be a registered tool.

#### Scenario: A client connects

- **WHEN** an MCP client initializes a session with the server
- **THEN** the response carries the instructions text
- **AND** it names `skill://solidworks-mcp/SKILL.md`

#### Scenario: The instructions name a removed tool

- **WHEN** a tool named in the instructions is no longer registered
- **THEN** the test suite fails, naming the tool

