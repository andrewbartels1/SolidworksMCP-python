# SolidWorks MCP Server

Python MCP server for SolidWorks automation with 70+ tools (modeling, sketching, drawing, export, analysis, automation, templates, and macros).

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://www.microsoft.com/windows)

## What Works (Verified Windows Setup)

This is the setup path that was validated end-to-end:

1. Install Python from python.org (Windows installer).
2. Enable **Add python.exe to PATH** during install.
3. Install this project into a local `.venv`.
4. Launch MCP from `.venv\Scripts\python.exe` (not from WSL).

When this is correct, startup logs show:

- `Platform: Windows`
- `SolidWorks COM interface is available`
- `Registered 76 SolidWorks tools`
- `Connected to SolidWorks`

## Requirements

- Windows 10/11 for real SolidWorks COM automation.
- Python 3.11+ from python.org.
- Git.
- SolidWorks installed and launched at least once.

Linux/WSL is still useful for docs/tests/mock mode, but not for direct COM automation.

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

- [Installation](docs/getting-started/installation.md)
- [Quick Start](docs/getting-started/quickstart.md)
- [VS Code MCP Setup](docs/getting-started/vscode-mcp-setup.md)
- [Architecture](docs/user-guide/architecture.md)

## License

MIT License. See [LICENSE](LICENSE).
