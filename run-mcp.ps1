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

function Test-PythonExecutable {
	param(
		[string]$PythonPath
	)

	if (-not (Test-Path $PythonPath)) {
		return $false
	}

	try {
		& $PythonPath -c "import sys" | Out-Null
		return $LASTEXITCODE -eq 0
	}
	catch {
		return $false
	}
}

function Get-UvExecutable {
	$candidatePaths = @(
		(Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
		(Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe"),
		(Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe"),
		(Join-Path $env:APPDATA "Python\Scripts\uv.exe"),
		(Join-Path $scriptDir ".venv\Scripts\uv.exe")
	)

	$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
	if ($uvCommand -and $uvCommand.Source) {
		return $uvCommand.Source
	}

	foreach ($candidatePath in $candidatePaths) {
		if ($candidatePath -and (Test-Path $candidatePath)) {
			return $candidatePath
		}
	}

	return $null
}

if (-not (Test-Path $startServerScript)) {
	Write-Error "Start server script not found: $startServerScript"
	exit 1
}

if (Test-PythonExecutable $venvPython) {
	& $venvPython $startServerScript @args
	exit $LASTEXITCODE
}

 $uvExecutable = Get-UvExecutable
if ($uvExecutable) {
	& $uvExecutable run --project $scriptDir python $startServerScript @args
	exit $LASTEXITCODE
}

Write-Error "No usable Python runtime found. Checked $venvPython and uv. Recreate the environment with 'uv venv' and reinstall dependencies if needed."
exit 1
