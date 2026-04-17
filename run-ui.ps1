# PowerShell script to run the FastAPI UI backend and Prefab dashboard frontend.
# Similar to run-mcp.ps1, this script provides a single entry point for local UI startup.
#
# Usage:
#   .\run-ui.ps1
#   .\run-ui.ps1 -BackendPort 8766 -FrontendPort 5175
#   .\run-ui.ps1 -Probe
#   .\run-ui.ps1 -NoNewWindows
#   .\run-ui.ps1 -DryRun

param(
    [int]$BackendPort = 8766,
    [int]$FrontendPort = 5175,
    [string]$FrontendTarget = "src/solidworks_mcp/ui/prefab_dashboard.py",
    [switch]$Probe,
    [switch]$NoNewWindows,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcPath = Join-Path $scriptDir "src"
$probeTarget = "src/solidworks_mcp/ui/prefab_trace_probe.py"

if ($Probe) {
    $FrontendTarget = $probeTarget
}

if ([string]::IsNullOrWhiteSpace($FrontendTarget)) {
    Write-Error "FrontendTarget cannot be empty. Use -Probe for the trace app or pass a valid file path."
    exit 1
}

$resolvedFrontendTarget = Join-Path $scriptDir $FrontendTarget
if (-not (Test-Path $resolvedFrontendTarget)) {
    Write-Error "Frontend target not found: $FrontendTarget"
    exit 1
}

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
$venvPrefab = Join-Path $scriptDir ".venv\Scripts\prefab.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error "Virtual environment python not found: $venvPython"
    exit 1
}

# If prefab.exe is missing, try to install prefab-ui then re-check.
# This handles fresh installs where pip may not have written the console script.
if (-not (Test-Path $venvPrefab)) {
    Write-Host "prefab.exe not found - installing/repairing prefab-ui..." -ForegroundColor Yellow
    & $venvPython -m pip install --quiet --force-reinstall "prefab-ui>=0.19.0"
    if (-not (Test-Path $venvPrefab)) {
        # Final fallback: invoke via python -m prefab_ui.cli (no .exe needed)
        Write-Host "prefab.exe still missing; falling back to 'python -m prefab_ui.cli'." -ForegroundColor Yellow
        $venvPrefab = $null  # signal to use module path
    }
}

# Build command strings for the two processes
$backendCmd = "`"$venvPython`" -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port $BackendPort --reload --reload-dir src"
$backendShellCommand = "Set-Location -LiteralPath '$scriptDir'; `$env:PYTHONPATH='$srcPath'; & '$venvPython' -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port $BackendPort --reload --reload-dir src"

if ($venvPrefab) {
    $frontendCmd = "`"$venvPrefab`" serve $FrontendTarget --port $FrontendPort --reload"
    $frontendShellCommand = "Set-Location -LiteralPath '$scriptDir'; `$env:SOLIDWORKS_UI_API_ORIGIN='http://127.0.0.1:$BackendPort'; `$env:PYTHONUTF8='1'; & '$venvPrefab' serve $FrontendTarget --port $FrontendPort --reload"
} else {
    $frontendCmd = "`"$venvPython`" -m prefab_ui.cli serve $FrontendTarget --port $FrontendPort --reload"
    $frontendShellCommand = "Set-Location -LiteralPath '$scriptDir'; `$env:SOLIDWORKS_UI_API_ORIGIN='http://127.0.0.1:$BackendPort'; `$env:PYTHONUTF8='1'; & '$venvPython' -m prefab_ui.cli serve $FrontendTarget --port $FrontendPort --reload"
}

$backendArgs = @(
    "-m",
    "uvicorn",
    "solidworks_mcp.ui.server:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$BackendPort",
    "--reload",
    "--reload-dir",
    "src"
)

# Build frontend args depending on whether prefab.exe exists
if ($venvPrefab) {
    $frontendExe = $venvPrefab
    $frontendArgs = @(
        "serve",
        $FrontendTarget,
        "--port",
        "$FrontendPort",
        "--reload"
    )
} else {
    $frontendExe = $venvPython
    $frontendArgs = @(
        "-m",
        "prefab_ui.cli",
        "serve",
        $FrontendTarget,
        "--port",
        "$FrontendPort",
        "--reload"
    )
}

Write-Host "Starting SolidWorks UI stack" -ForegroundColor Cyan
Write-Host "- Backend : http://127.0.0.1:$BackendPort" -ForegroundColor Yellow
Write-Host "- OpenAPI : http://127.0.0.1:$BackendPort/docs" -ForegroundColor Yellow
Write-Host "- Frontend: http://127.0.0.1:$FrontendPort" -ForegroundColor Yellow
Write-Host "- Target  : $FrontendTarget" -ForegroundColor Yellow
Write-Host ""

if ($DryRun) {
    Write-Host "Dry run enabled. Commands:" -ForegroundColor Green
    Write-Host "Backend : $backendCmd"
    Write-Host "Frontend: $frontendCmd"
    exit 0
}

if ($NoNewWindows) {
    Write-Host "Running backend and frontend in background jobs in this shell..." -ForegroundColor Cyan

    Start-Job -Name "solidworks-ui-backend" -ScriptBlock {
        param($workingDir, $pythonExe, $argsArray, $pythonPath)
        Set-Location $workingDir
        $env:PYTHONPATH = $pythonPath
        & $pythonExe @argsArray
    } -ArgumentList $scriptDir, $venvPython, $backendArgs, $srcPath | Out-Null

    Start-Job -Name "solidworks-ui-frontend" -ScriptBlock {
        param($workingDir, $prefabExe, $argsArray, $apiOrigin)
        Set-Location $workingDir
        $env:SOLIDWORKS_UI_API_ORIGIN = $apiOrigin
        $env:PYTHONUTF8 = "1"
        & $prefabExe @argsArray
    } -ArgumentList $scriptDir, $frontendExe, $frontendArgs, "http://127.0.0.1:$BackendPort" | Out-Null

    Write-Host "Started jobs: solidworks-ui-backend, solidworks-ui-frontend" -ForegroundColor Green
    Write-Host "Use Get-Job / Receive-Job / Stop-Job to monitor and stop." -ForegroundColor Yellow
    exit 0
}

Write-Host "Launching two PowerShell windows..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $backendShellCommand
)
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $frontendShellCommand
)

Write-Host "UI stack launch requested." -ForegroundColor Green
