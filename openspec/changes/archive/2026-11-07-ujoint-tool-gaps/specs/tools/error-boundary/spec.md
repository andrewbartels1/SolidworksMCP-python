## ADDED Requirements

### Requirement: A plain dict is accepted as a tool's input

The tool boundary SHALL validate a dict passed where a tool expects its input model, so every tool can be called from a script with a dict.

#### Scenario: A script passes a dict
- **WHEN** a script calls `check_interference` with `{"components": ["a-1", "b-1"]}`
- **THEN** the tool runs as it would over MCP

#### Scenario: A bad dict
- **WHEN** the dict fails validation
- **THEN** the tool returns `error_type: invalid_input`, naming the field
