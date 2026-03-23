# VS Code MCP Setup

This page reflects the verified Windows setup that works with Python from python.org.

## Before You Start

- Python installed from python.org.
- PATH enabled for `python`.
- Project installed in `.venv` with `pip install -e .`.
- SolidWorks installed if you want real COM automation.

## Open MCP Config

1. In VS Code, open Command Palette (`Ctrl+Shift+P`).
2. Run `MCP: Open User Configuration`.
3. Edit `%APPDATA%\Code\User\mcp.json`.

## Recommended Configuration (Windows, verified)

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

This avoids environment activation issues by using the project script that launches `.venv\Scripts\python.exe` directly.

<details>
<summary><b>Alternative: direct venv python command</b></summary>

```json
{
  "servers": {
    "solidworks-mcp-server": {
      "type": "stdio",
      "command": "C:\\path\\to\\SolidworksMCP-python\\.venv\\Scripts\\python.exe",
      "args": ["-m", "solidworks_mcp.server"]
    }
  }
}
```

</details>

<details>
<summary><b>Alternative: Linux/WSL mock mode only</b></summary>

Use this for docs/tests or mock-mode development only (not real SolidWorks COM control).

```json
{
  "servers": {
    "solidworks-mcp-server": {
      "type": "stdio",
      "command": "C:\\Windows\\System32\\wsl.exe",
      "args": [
        "-d",
        "YOUR_WSL_DISTRO",
        "--",
        "/home/YOUR_USERNAME/.local/bin/micromamba",
        "run",
        "-n",
        "solidworks_mcp",
        "python",
        "-m",
        "solidworks_mcp.server"
      ]
    }
  }
}
```

</details>

## Validate Startup

After saving `mcp.json`, start server `solidworks-mcp-server` in VS Code and check logs.

Healthy logs should include:

- `Platform: Windows`
- `SolidWorks COM interface is available`
- `Registered 76 SolidWorks tools`
- `Connected to SolidWorks`

## Troubleshooting

### `ModuleNotFoundError: solidworks_mcp`

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

### `ModuleNotFoundError: fastmcp`

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

### `python` points to Microsoft Store alias

- Disable App execution alias for Python in Windows settings.
- Reinstall Python from python.org and enable PATH.

### Server starts but tool actions fail

- Start SolidWorks first.
- Ensure server is running on Windows, not WSL, for COM actions.
