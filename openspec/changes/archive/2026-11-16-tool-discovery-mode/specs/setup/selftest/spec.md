## ADDED Requirements

### Requirement: The tool mode is reported
The self-test's environment section SHALL report the tool mode, the
active toolsets and the number of visible tools.

#### Scenario: A core-only setup
- **WHEN** `--selftest` runs with `SOLIDWORKS_MCP_TOOLSETS=core`
- **THEN** the report shows mode `list`, toolsets `core`, and the visible
  tool count
