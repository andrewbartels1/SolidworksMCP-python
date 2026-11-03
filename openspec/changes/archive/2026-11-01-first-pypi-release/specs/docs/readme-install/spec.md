## MODIFIED Requirements

### Requirement: One install path

The README SHALL give one install path: what is needed, installing uv, and
`uvx solidworks-mcp-python setup`, then what a working server prints.
Installing from a clone SHALL be on the docs Installation page, not in the
README's Install section.

#### Scenario: A first-time user installs the server

- **WHEN** a user with Windows and SolidWorks follows the Install section
- **THEN** they run one command to install uv and one to run setup
- **AND** the section says how to tell that it worked

#### Scenario: A contributor installs from source

- **WHEN** a user follows the README's link for installing from a clone
- **THEN** the docs Installation page gives the clone and `install.ps1` steps

### Requirement: One config per client, all launching the server the same way

The README SHALL have one collapsible entry for each of Claude Desktop,
Claude Code, VS Code and LM Studio. Each entry SHALL say where the config
lives, give one config or command, and say how to confirm the client
connected. Every entry SHALL launch the server with `uvx` and the argument
`solidworks-mcp-python`, with no local paths.

#### Scenario: A user sets up Claude Desktop

- **WHEN** a user opens the Claude Desktop entry
- **THEN** they see where `claude_desktop_config.json` lives (classic and
  packaged installs), one JSON block to add, and how to confirm the server
  is connected

#### Scenario: The launch is the same for every client

- **WHEN** the four entries are compared
- **THEN** each starts `uvx solidworks-mcp-python`, and none contains a
  folder path

## ADDED Requirements

### Requirement: Only tested SolidWorks versions are claimed

The README SHALL name only SolidWorks versions the server has been tested
on as supported. Any other version SHALL be described as untested.

#### Scenario: The version badge

- **WHEN** a visitor reads the README's badges
- **THEN** the SolidWorks badge says it was tested on 2026, not a range
