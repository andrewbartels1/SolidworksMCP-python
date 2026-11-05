## MODIFIED Requirements

### Requirement: One config per client, all launching the server the same way

The README SHALL have one collapsible entry for each of Claude Desktop,
Claude Code, VS Code and LM Studio. Each entry SHALL say where the config
lives, give one config or command, and say how to confirm the client
connected. Every entry SHALL launch the server with `uvx` and the arguments
`solidworks-mcp-python --year <year>`, with no local paths, and the README
SHALL say that `--year` names the installed SolidWorks release and is
required for real SolidWorks.

#### Scenario: A user sets up Claude Desktop

- **WHEN** a user opens the Claude Desktop entry
- **THEN** they see where `claude_desktop_config.json` lives (classic and
  packaged installs), one JSON block to add, and how to confirm the server
  is connected

#### Scenario: The launch is the same for every client

- **WHEN** the four entries are compared
- **THEN** each starts `uvx solidworks-mcp-python --year 2026`, and none
  contains a folder path
