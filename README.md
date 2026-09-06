# SolidWorks CAD Assistant & MCP Server

**Languages:** [English](README.md) | [Español](README.es-ES.md)

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://www.microsoft.com/windows)
[![SolidWorks](https://img.shields.io/badge/SolidWorks-2019--2026-red)](https://www.solidworks.com/)
[![Coverage](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python/branch/main/graph/badge.svg)](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python)

Python MCP server for SolidWorks automation with 129 tools, plus an optional agent/prompt-testing layer for AI-assisted workflows.

## Overview

> ⚠️ **Project Status:** This project is under active construction. Features, APIs, documentation, and setup steps may change as the Python and UI implementation is finalized. This is a hobby/research product, please feel free to make an issue if you have questions or feedback! ⚠️

This project focuses on practical SolidWorks automation with an AI-friendly loop:

1. describe intent
2. generate a plan
3. execute MCP tools
4. inspect results
5. iterate

It includes:

- core MCP runtime for SolidWorks tool execution
- COM/VBA routing and adapter safety wrappers
- tool coverage across modeling, sketching, drawing, analysis, export, automation, templates, and macros
- optional agent orchestration/testing utilities under `src/solidworks_mcp/agents/`

## Supported Today

- Windows + SolidWorks COM automation for the main CAD lifecycle.
- Modeling, sketching, drawing, analysis, export, automation, templates, and macro tools.

## Not Yet / Simulated

- Mock adapter output is simulated and should not be treated as engineering truth.
- Live 3D viewport streaming in a UI.
- Checkpoint-level interference validation.
- Simple simulation and fluid workflows
- Simple Topology Optimization via SimulationXpress etc.

## What Works (Verified Windows Setup)

This is the setup path validated end-to-end:

1. Install Python from python.org (Windows installer).
2. Enable **Add python.exe to PATH** during install.
3. Install this project into a local `.venv`.
4. Launch MCP from `.venv\Scripts\python.exe` (not from WSL).

When this is correct, startup logs show:

- `Platform: Windows`
- `SolidWorks COM interface is available`
- `Registered ... SolidWorks tools` (count varies as tools evolve)
- `Connected to SolidWorks`

## Requirements

- Windows 10/11 for real SolidWorks COM automation.
- Python 3.13+ from python.org.
- Git.
- SolidWorks installed and launched at least once.

Linux/WSL is useful for docs/tests/mock mode, but not for direct COM automation.

## Quick Start (Windows, python.org)

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e .
```

Start server manually:

```powershell
.\.venv\Scripts\python.exe -m solidworks_mcp.server
```

Or use the helper script (open SolidWorks first):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deployment\run-mcp.ps1 --real --year 2026
```

> **Mock mode warning** — running `run-mcp.ps1` without `--real` starts the
> server in mock mode.  All tool responses are simulated; nothing touches
> SolidWorks.  Always pass `--real --year <year>` for live automation.

## Development Commands

Use the helper script for common workflows:

```powershell
.\dev-commands.ps1
```

Common commands:

- `dev-install` - install/update local dev environment
- `dev-test` - run standard test suite (CI-safe subset)
- `dev-test-full` - run full test suite (includes smoke/integration paths)
- `dev-lint` - lint checks
- `dev-format` - format code
- `dev-docs-build` - build docs site once
- `dev-docs-strict` - strict docs build (fails on warnings)
- `dev-docs-audit` - generate docs audit report in `.generated/docs`

### Local CI Replica (Docker)

To mirror GitHub Actions CI locally (Ubuntu + conda env from `solidworks_mcp.yml` + `make test`), run:

```powershell
.\run-ci-local.ps1
```

The first run builds the image. Re-run without rebuild when only executing tests:

```powershell
.\run-ci-local.ps1 -NoBuild
```

## MCP Client Configuration (Windows)

There are two parallel sets of launch scripts, both in `deployment/`:

- `deployment/run-mcp.ps1` / `src/utils/start_local_server.py` — the local
  dev/demo harness: decorative startup banners, an HTTP health-check step,
  and an example tool-call workflow. Good for running by hand in a terminal
  to see what the server does. **Not recommended for MCP host configs** — a
  stdio MCP host treats a spawned server's stdout as a pure JSON-RPC
  channel, and this script's banner output goes to stdout.
- `deployment/run-mcp-claude.ps1` / `src/utils/start_local_server_claude.py`
  — a minimal entrypoint with no decorative output, meant specifically for
  MCP host configs (Claude Desktop, Claude Code, VS Code, LM Studio). Use
  these for any host config below.

> **If a tool call fails with an error like `invalid_union` / "expected
> object, received string"** — that's the client's JSON-RPC parser choking
> on non-JSON text. It almost always means the config's `args` point at
> `start_local_server.py` (or `run-mcp.ps1`) instead of the `_claude`
> variant. This is easy to hit after editing a config by hand or letting a
> client's own "fix it for me" assistant rewrite the command: it may resolve
> the path to the plain script by filename guess. Check the exact filename
> in your config against the list above.

MCP hosts spawn servers over raw stdio pipes with no console attached.
Windows PowerShell's native-command invocation is unreliable in that exact
scenario — `run-mcp-claude.ps1`'s venv-detection step uses `Start-Process`
instead of piping to `Out-Null` to avoid it (piping a native command's
output makes it a pipeline stage, which throws `Cannot run a document in
the middle of a pipeline` when there's no console attached to the host
process). If you still hit connection failures with it, point the client
directly at the venv's `python.exe` instead, which skips PowerShell
entirely.

### Claude Desktop

Claude Desktop reads its MCP server list from a `claude_desktop_config.json` file. The path depends on how the app was installed:

- Classic/legacy installs: `%APPDATA%\Claude\claude_desktop_config.json`
- Packaged (MSIX-style) installs: `%LOCALAPPDATA%\Packages\Claude_<hash>\LocalCache\Roaming\Claude\claude_desktop_config.json` — look under `%LOCALAPPDATA%\Packages\` for a folder starting with `Claude_` if the classic path doesn't exist.

Create the file if it doesn't exist yet, and use the server key `solidworks` (the troubleshooting runbook in [CLAUDE.md](CLAUDE.md) and the app's own log filenames assume this name). If the file already has other top-level keys (preferences, etc.), just add `mcpServers` alongside them — don't replace the file:

```json
{
  "mcpServers": {
    "solidworks": {
      "command": "C:\\path\\to\\SolidworksMCP-python\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\path\\to\\SolidworksMCP-python\\src\\utils\\start_local_server_claude.py",
        "--real",
        "--year",
        "2026"
      ]
    }
  }
}
```

Replace the paths with your local repository path. The `--real --year 2026` flags start the server in live COM automation mode (requires SolidWorks already open). Omit them for mock mode.

After saving, **fully quit Claude Desktop** (not just close the window — use File > Exit or the tray icon) and relaunch it so it reloads the MCP server list. To confirm it picked up the server:

- In the app, open **Settings > Developer** and check that `solidworks` is listed and connected.
- Or check `%LOCALAPPDATA%\Claude\Logs\mcp-server-solidworks.log` for a full `initialize` / `tools/list` round trip.
- Tool-call errors are logged separately; see [Troubleshooting Runbook](CLAUDE.md#troubleshooting-runbook) in CLAUDE.md if the server appears but tool calls fail.

### VS Code

Set your user MCP config (`%APPDATA%\Code\User\mcp.json`) to:

```json
{
  "servers": {
    "solidworks-mcp-server": {
      "type": "stdio",
      "command": "powershell",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:\\path\\to\\SolidworksMCP-python\\deployment\\run-mcp.ps1",
        "--real",
        "--year",
        "2026"
      ]
  },
  "inputs": []
}
```

Replace the script path with your local repository path.  The `--real --year 2026` flags start the server in live COM automation mode (requires SolidWorks open).  Omit them for mock mode.

If this doesn't connect (see the note above about stdio hosts and stdout), switch to the MCP-host-safe wrapper below.

#### Recommended for MCP use: run-mcp-claude.ps1

```json
{
  "servers": {
    "solidworks-mcp-server": {
      "type": "stdio",
      "command": "powershell",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:\\path\\to\\SolidworksMCP-python\\deployment\\run-mcp-claude.ps1",
        "--real",
        "--year",
        "2026"
      ]
  },
  "inputs": []
}
```

### LM Studio

Set your LM Studio MCP config file to include this server (LM Studio expects `mcpServers`):

```json
{
  "mcpServers": {
    "solidworks-mcp-server": {
      "command": "C:\\path\\to\\SolidworksMCP-python\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\path\\to\\SolidworksMCP-python\\src\\utils\\start_local_server_claude.py",
        "--real",
        "--year",
        "2026"
      ]
    }
  }
}
```

After saving, restart LM Studio so it reloads MCP servers.

## Optional Features (environment toggles)

All off/default unless set. Pass these as environment variables when launching
the server (or in your MCP host config's `env` block); every
`SOLIDWORKS_MCP_<FIELD>` maps to a config field of the same name.

### SolidWorks-as-Code session logging — **off by default**

Logs every adapter tool call to a local SQLite database so a session can be
replayed or exported as a runnable Python script (see
[docs/getting-started/solidworks-as-code.md](docs/getting-started/solidworks-as-code.md)).

| Variable | Default | Meaning |
| --- | --- | --- |
| `SOLIDWORKS_MCP_SOC_LOGGING_ENABLED` | `false` | Turn logging on. |
| `SOLIDWORKS_MCP_SOC_SESSION_ID` | *(generated)* | Session name to log under. If unset while logging is on, a `soc-YYYYMMDD-HHMMSS` id is generated at startup. |
| `SOLIDWORKS_MCP_SOC_DB_PATH` | `.solidworks_mcp/agent_memory.sqlite3` | Override the database file. |

```powershell
$env:SOLIDWORKS_MCP_SOC_LOGGING_ENABLED = "true"
$env:SOLIDWORKS_MCP_SOC_SESSION_ID = "my-bracket"
.\.venv\Scripts\python.exe -m solidworks_mcp.server
# ...work in your MCP client...
.\.venv\Scripts\python.exe -m solidworks_mcp.agents.soc_exporter my-bracket my_bracket.py
```

Effective only with the circuit-breaker adapter wrapper (the default for real
SolidWorks); the mock adapter does not log.

### API docs index auto-refresh — **on by default**

The granular API-lookup tools (`lookup_api_interface`, `lookup_api_method`,
`find_related_api_members`) and `search_solidworks_api_help` read a JSON index
built by `discover_solidworks_docs`. When that index is older than the
threshold it is rebuilt automatically on the next lookup.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SOLIDWORKS_MCP_DOCS_INDEX_AUTO_REFRESH` | `true` | Rebuild a stale index automatically. No-op without SolidWorks + win32com; a failed rebuild keeps serving the existing index. |
| `SOLIDWORKS_MCP_DOCS_INDEX_MAX_AGE_DAYS` | `21` | Age after which the index counts as stale. |

## Common Windows Fixes

If `python` is not found:

```powershell
python --version
```

If this opens Microsoft Store or fails, reinstall Python from python.org and enable PATH.

If startup fails with `ModuleNotFoundError: solidworks_mcp`:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

If startup fails with `ModuleNotFoundError: fastmcp`:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

## Docs

- Main docs site: <https://andrewbartels1.github.io/SolidworksMCP-python/>
- Home/overview: [docs/index.md](docs/index.md)

Key docs sections:

- Getting Started: [docs/getting-started](docs/getting-started)
- MCP Server Guide: [docs/user-guide](docs/user-guide)
- Tool Catalog: [docs/user-guide/tool-catalog](docs/user-guide/tool-catalog)
- Agents and Skills: [docs/agents](docs/agents)
- Planning/Roadmap: [docs/planning](docs/planning)

Direct links:

- [Installation](docs/getting-started/installation.md)
- [Quick Start](docs/getting-started/quickstart.md)
- [Tutorial: U-Joint Assembly Build](docs/getting-started/tutorials/u-joint-assembly-build.md)
- [Tutorial Tracks](docs/getting-started/tutorial-tracks.md)
- [VS Code MCP Setup](docs/getting-started/vscode-mcp-setup.md)
- [Architecture](docs/user-guide/architecture.md)
- [Agents and Prompt Testing](docs/agents/agents-and-testing.md)
- [PydanticAI and Schemas](docs/agents/pydantic-ai-and-schemas.md)

## License

MIT License. See [LICENSE](LICENSE).
