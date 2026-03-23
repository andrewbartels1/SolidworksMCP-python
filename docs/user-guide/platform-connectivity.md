# Platform and Connectivity

This guide explains how to run SolidWorks MCP when your day-to-day workflow is Linux/WSL but real SolidWorks automation must run on Windows.

## Mental Model

- SolidWorks + COM bridge live on Windows.
- Your editor, tests, docs, and most development can run on Linux/WSL.
- Linux/WSL clients connect to the Windows-hosted MCP server in remote HTTP mode.

## Typical Setup Patterns

| Pattern | Works for tests/docs | Works for real SolidWorks automation |
| --- | --- | --- |
| Windows only | Yes | Yes |
| WSL/Linux only | Yes | No |
| WSL/Linux dev + Windows host server | Yes | Yes |
| Linux container only | Yes | No |

## Start Server on Windows Host

=== "Windows (PowerShell)"
    ```powershell
    .\.venv\Scripts\python.exe -m solidworks_mcp.server --mode remote --host 0.0.0.0 --port 8000
    ```

Equivalent local stdio start:

=== "Windows (PowerShell)"
    ```powershell
    powershell -NoProfile -ExecutionPolicy Bypass -File .\run-mcp.ps1
    ```

## Connect From Linux / WSL Client

Remote clients (including Linux/WSL machines) can connect to the Windows host running the MCP server in remote mode using the server's IP address and port.

## Verify SolidWorks Is Actually Reachable

Run these checks on Windows where SolidWorks is installed.

=== "Windows (PowerShell)"
    ```powershell
    .\.venv\Scripts\python.exe -c "import win32com.client; print('win32com import OK')"
    .\.venv\Scripts\python.exe -c "import win32com.client as w; app=w.Dispatch('SldWorks.Application'); print('SldWorks COM dispatch OK')"
    ```

If COM dispatch fails:

1. Launch SolidWorks manually once, then try again.
2. Ensure you are using Windows Python (not WSL Python) for this check.
3. Reinstall/repair `pywin32` inside the active environment.

## Container Notes

Containers are useful for:

- Running tests in mock mode
- Linting and docs builds
- CI pipelines

Containers are not sufficient by themselves for real SolidWorks automation because COM and SolidWorks are Windows-native.

## Recommended Beginner Workflow

1. Install and open SolidWorks on Windows.
2. Install repo dependencies and run the server on Windows.
3. Develop and run most tests on Linux/WSL.
4. For real CAD verification, call the Windows-hosted server.
