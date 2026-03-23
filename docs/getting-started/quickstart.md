# Quick Start Guide

Get running quickly with the verified Windows setup.

## Prerequisites

- Python 3.11+ installed from python.org.
- PATH enabled during Python install.
- Windows 10/11.
- SolidWorks installed (for real automation).

## 1. Install

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e .
```

## 2. Configure VS Code MCP

Set `%APPDATA%\Code\User\mcp.json`:

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

Replace the script path with your local repository location.

## 3. Start Server

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-mcp.ps1
```

Expected log markers:

- `Platform: Windows`
- `SolidWorks COM interface is available`
- `Registered 76 SolidWorks tools`
- `Connected to SolidWorks`

## 4. First Connection Check

```python
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.config import load_config

config = load_config()
adapter = PyWin32Adapter(config)
result = adapter.connect()
print(f"Connection status: {result['status']}")
```

## 5. Basic Bracket Example

```python
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.config import load_config

config = load_config()
adapter = PyWin32Adapter(config)

# New part
adapter.create_new_document("part")

# Base sketch
adapter.create_sketch("Front Plane")
adapter.add_rectangle(0, 0, 50, 30)
adapter.exit_sketch()

# Extrude base
adapter.create_extrusion({"distance": 10})

# Add two holes
adapter.create_sketch("Top Face")
adapter.add_circle(10, 10, 2.5)
adapter.add_circle(40, 10, 2.5)
adapter.exit_sketch()
adapter.create_extrusion({"distance": 10, "cut": True})

print("Bracket created")
```

## Troubleshooting

### `python` command fails

Reinstall Python from python.org and ensure PATH option is enabled.

### `ModuleNotFoundError: solidworks_mcp`

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

### `ModuleNotFoundError: fastmcp`

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

### SolidWorks tool actions fail

- Start SolidWorks before MCP.
- Confirm you are on Windows.
- Check COM availability:

```powershell
.\.venv\Scripts\python.exe -c "import win32com.client; print('win32com OK')"
```
