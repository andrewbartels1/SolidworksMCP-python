## Purpose

The README takes a first-time user from nothing to an MCP client connected
to SolidWorks, with one install path and one config per client.

## ADDED Requirements

### Requirement: One install path

The README SHALL give one install path: what is needed, one block of
commands, and what a working server prints.

#### Scenario: A first-time user installs the server

- **WHEN** a user with Windows, SolidWorks and Python 3.13 follows the
  Install section
- **THEN** they run one block of commands and have the server installed in
  the project's `.venv`
- **AND** the section says how to tell that it worked

### Requirement: One config per client, all launching the server the same way

The README SHALL have one collapsible entry for each of Claude Desktop,
Claude Code, VS Code and LM Studio. Each entry SHALL say where the config
lives, give one config or command, and say how to confirm the client
connected. Every entry SHALL launch the server with the same executable and
arguments.

#### Scenario: A user sets up Claude Desktop

- **WHEN** a user opens the Claude Desktop entry
- **THEN** they see where `claude_desktop_config.json` lives (classic and
  packaged installs), one JSON block to add, and how to confirm the server
  is connected

#### Scenario: The launch is the same for every client

- **WHEN** the four entries are compared
- **THEN** each starts the same executable, with the same arguments

### Requirement: Troubleshooting lives in the docs

Launcher internals and error explanations SHALL be on the docs Installation
page under Troubleshooting, and the README SHALL link there instead of
including them.

#### Scenario: A tool call fails with `invalid_union`

- **WHEN** a user follows the README's troubleshooting link
- **THEN** the docs page explains the error, its cause and the fix
