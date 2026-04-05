# PowerShell script to run SolidWorks MCP Server from Windows Python
# This is a thin wrapper around start_local_server.py to provide a single entry point.
#
# Usage:
#   .\run-mcp.ps1              -- mock mode (no SolidWorks required, for testing)
#   .\run-mcp.ps1 --real       -- real SolidWorks COM adapter (SolidWorks must be open)
#   .\run-mcp.ps1 --real --year 2026 --log-level DEBUG  -- real mode with verbose logging
#
# VS Code mcp.json should pass --real --year <year> --log-level DEBUG for live design work.
$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
$startServerScript = Join-Path $scriptDir "src\utils\start_local_server.py"

if (-not (Test-Path $venvPython)) {
	Write-Error "Virtual environment python not found: $venvPython"
	exit 1
}

if (-not (Test-Path $startServerScript)) {
	Write-Error "Start server script not found: $startServerScript"
	exit 1
}

# Run the local server startup script (canonical entry point)
# Pass through all arguments to the Python script
& $venvPython $startServerScript @args
