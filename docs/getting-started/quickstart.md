# Quick Start Guide

Get running quickly with the verified Windows setup.

## Prerequisites

- Windows 10/11.
- SolidWorks installed (for real automation).

## 1. Install and connect your client

Install [uv](https://docs.astral.sh/uv/), open a new PowerShell window, and run setup:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uvx solidworks-mcp-python setup
```

uv fetches Python and the server from PyPI. Setup:

1. finds your SolidWorks and your MCP clients (Claude Desktop, Claude Code, VS Code, Cursor, LM Studio);
2. lets you pick which to connect;
3. checks that the server starts;
4. adds a `solidworks` entry to each client you picked.

Run `uvx solidworks-mcp-python setup` again any time to add a client. To work on the server itself, [install from source](installation.md#install-from-source). The [Installation guide](installation.md) covers each step and the options.

## 2. Check it works

Open SolidWorks, restart your client as setup told you, and ask *"What model is open in SolidWorks?"*. The server's log includes:

- `SolidWorks COM interface is available`
- `Registered 154 SolidWorks tools` (the count grows as tools are added)
- `Connected to SolidWorks`

If it says `Could not connect to SolidWorks`, SolidWorks wasn't open when the server started. Open it and restart the server from your client.

To set a client up by hand instead, every client runs the same command, `uvx solidworks-mcp-python`. The README's [Connect your client](https://github.com/andrewbartels1/SolidworksMCP-python#connect-your-client) section has the config for each.

## 3. Optional: start the server by hand

Clients start the server themselves. To watch its log in a terminal instead, open SolidWorks and run:

```powershell
uvx solidworks-mcp-python
```

It waits for an MCP client on stdin; stop it with `Ctrl+C`.

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

### Tools return blank images or fake data

The server is in mock mode.  Ensure `--real --year 2026` appears in your
`mcp.json` args after the script path, then restart the server.

### SolidWorks tool actions fail

- Open SolidWorks **before** starting the MCP server.
- Confirm `--real` is in the server args (see above).
- Confirm you are on Windows (COM does not work in WSL).
- Check COM availability:

```powershell
.\.venv\Scripts\python.exe -c "import win32com.client; print('win32com OK')"
```
