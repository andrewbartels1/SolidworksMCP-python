# PowerShell script to run the FastAPI UI backend and Prefab dashboard frontend.
# Similar to run-mcp.ps1, this script provides a single entry point for local UI startup.
#
# Usage:
#   .\run-ui.ps1
#   .\run-ui.ps1 -BackendPort 8766 -FrontendPort 5175
#   .\run-ui.ps1 -NoNewWindows
#   .\run-ui.ps1 -DryRun

param(
    [int]$BackendPort = 8766,
    [int]$FrontendPort = 5175,
    [switch]$NoNewWindows,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
$venvPrefab = Join-Path $scriptDir ".venv\Scripts\prefab.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error "Virtual environment python not found: $venvPython"
    exit 1
}

if (-not (Test-Path $venvPrefab)) {
    Write-Error "Prefab executable not found: $venvPrefab"
    exit 1
}

$backendCmd = "`"$venvPython`" -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port $BackendPort --reload"
$frontendCmd = "`"$venvPrefab`" serve src/solidworks_mcp/ui/prefab_dashboard.py --port $FrontendPort --reload"
$backendShellCommand = "& { Set-Location -LiteralPath '$scriptDir'; & '$venvPython' -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port $BackendPort --reload }"
$frontendShellCommand = "& { Set-Location -LiteralPath '$scriptDir'; `$env:SOLIDWORKS_UI_API_ORIGIN='http://127.0.0.1:$BackendPort'; `$env:PYTHONUTF8='1'; & '$venvPrefab' serve src/solidworks_mcp/ui/prefab_dashboard.py --port $FrontendPort --reload }"

$backendArgs = @(
    "-m",
    "uvicorn",
    "solidworks_mcp.ui.server:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$BackendPort",
    "--reload"
)

$frontendArgs = @(
    "serve",
    "src/solidworks_mcp/ui/prefab_dashboard.py",
    "--port",
    "$FrontendPort",
    "--reload"
)

Write-Host "Starting SolidWorks UI stack" -ForegroundColor Cyan
Write-Host "- Backend : http://127.0.0.1:$BackendPort" -ForegroundColor Yellow
Write-Host "- OpenAPI : http://127.0.0.1:$BackendPort/docs" -ForegroundColor Yellow
Write-Host "- Frontend: http://127.0.0.1:$FrontendPort" -ForegroundColor Yellow
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
        param($workingDir, $pythonExe, $argsArray)
        Set-Location $workingDir
        & $pythonExe @argsArray
    } -ArgumentList $scriptDir, $venvPython, $backendArgs | Out-Null

    Start-Job -Name "solidworks-ui-frontend" -ScriptBlock {
        param($workingDir, $prefabExe, $argsArray, $apiOrigin)
        Set-Location $workingDir
        $env:SOLIDWORKS_UI_API_ORIGIN = $apiOrigin
        $env:PYTHONUTF8 = "1"
        & $prefabExe @argsArray
    } -ArgumentList $scriptDir, $venvPrefab, $frontendArgs, "http://127.0.0.1:$BackendPort" | Out-Null

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
