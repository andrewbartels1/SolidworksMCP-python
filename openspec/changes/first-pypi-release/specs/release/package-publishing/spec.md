## Purpose

A tagged version of this server reaches users through PyPI, GitHub
Releases and the official MCP Registry, and starts with one `uvx` command.

## ADDED Requirements

### Requirement: A version tag publishes everywhere, or nowhere

Pushing a tag `v<version>` SHALL publish that version to PyPI as
`solidworks-mcp-python`, then create a GitHub Release with that version's
CHANGELOG section and the built files, and publish `server.json` to the
MCP Registry. If the tag differs from the version in `pyproject.toml`, the
package's `__version__`, or either version in `server.json`, nothing SHALL
be published.

#### Scenario: Versions disagree

- **WHEN** the tag is `v1.5.0` and `server.json` still says `1.4.0`
- **THEN** the release fails before building, and nothing is published

### Requirement: The package starts with uvx

The published package SHALL start the stdio server with
`uvx solidworks-mcp-python`, and `uvx solidworks-mcp-python setup` SHALL run
the guided client setup. `--help` SHALL list each option with a one-line
description and no internal text.

#### Scenario: Help on a fresh machine

- **WHEN** a user runs `uvx solidworks-mcp-python --help`
- **THEN** the output lists `--config`, `--mode`, `--host`, `--port`,
  `--debug` and `--mock`, each with one line of help
- **AND** it contains no `typer.Option` text

### Requirement: The PyPI page shows the README intact

The package description SHALL be the README with every relative image
source and relative link made absolute: images to their raw file on
GitHub, other links to the file on GitHub. It SHALL keep the
`mcp-name: io.github.andrewbartels1/solidworks-mcp-python` marker the MCP
Registry checks.

#### Scenario: A demo GIF on PyPI

- **WHEN** the README shows `docs/assets/....gif`
- **THEN** the package description shows it from
  `https://raw.githubusercontent.com/andrewbartels1/SolidworksMCP-python/main/docs/assets/....gif`

#### Scenario: The registry marker

- **WHEN** the built package's description is read
- **THEN** it contains `mcp-name: io.github.andrewbartels1/solidworks-mcp-python`
