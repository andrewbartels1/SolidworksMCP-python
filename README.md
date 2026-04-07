# SolidWorks MCP Server

Python MCP server for SolidWorks automation with 106 tools, plus an optional agent/prompt-testing layer for AI-assisted workflows.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://www.microsoft.com/windows)
[![SolidWorks](https://img.shields.io/badge/SolidWorks-2019--2025-red)](https://www.solidworks.com/)
[![Coverage](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python/branch/main/graph/badge.svg)](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python)

## Overview

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
- Python 3.11+ from python.org.
- Git.
- SolidWorks installed and launched at least once.

Linux/WSL is useful for docs/tests/mock mode, but not for direct COM automation at the moment, this is planned to be supported later after the codebase is working well and more stable.

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

Or use the helper script:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-mcp.ps1
```

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
- `dev-make-docs-build` - build docs site

## VS Code MCP Configuration (Windows)

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
        "C:\\path\\to\\SolidworksMCP-python\\run-mcp.ps1"
      ]
    }
  }
}
```

Replace the script path with your local repository path.

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
- [VS Code MCP Setup](docs/getting-started/vscode-mcp-setup.md)
- [Architecture](docs/user-guide/architecture.md)
- [Agents and Prompt Testing](docs/agents/agents-and-testing.md)
- [PydanticAI and Schemas](docs/agents/pydantic-ai-and-schemas.md)

## License

MIT License. See [LICENSE](LICENSE).
