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

The adapter methods are awaited because the PyWin32 adapter exposes its SolidWorks operations as `async` coroutines. If you call these methods without `await`, Python only creates a coroutine object and the COM operation never actually runs, which leads to warnings like `coroutine was never awaited`.

`asyncio.run(main())` starts an event loop so the awaited adapter calls can execute in order.

```python
import asyncio

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.config import load_config

async def main() -> None:
  config = load_config()
  adapter = PyWin32Adapter(config)
  await adapter.connect()
  print(f"Connected: {adapter.is_connected()}")

asyncio.run(main())
```

## 5. Basic Bracket Example

Every SolidWorks operation below is awaited for the same reason: each call is an async adapter method that performs COM work against the running SolidWorks instance. Using `await` ensures each step finishes before the next one starts, which is important for ordered CAD operations like sketch -> exit sketch -> extrude.

```python
import asyncio

from solidworks_mcp.adapters.base import ExtrusionParameters
from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter
from solidworks_mcp.config import load_config

async def main() -> None:
  config = load_config()
  adapter = PyWin32Adapter(config)
  await adapter.connect()

  # New part
  part_result = await adapter.create_part()
  if not part_result.is_success:
    raise RuntimeError(f"Failed to create part: {part_result.error}")

  # Base sketch
  await adapter.create_sketch("Front Plane")
  await adapter.add_rectangle(0, 0, 50, 30)
  await adapter.exit_sketch()

  # Extrude base
  await adapter.create_extrusion(ExtrusionParameters(depth=10))

  # Add two holes
  await adapter.create_sketch("Top Plane")
  await adapter.add_circle(10, 10, 2.5)
  await adapter.add_circle(40, 10, 2.5)
  await adapter.exit_sketch()
  await adapter.create_cut_extrude(ExtrusionParameters(depth=10))

  print("Bracket created")
  await adapter.disconnect()

asyncio.run(main())
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
