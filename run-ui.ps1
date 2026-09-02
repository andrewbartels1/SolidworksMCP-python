# PowerShell script to run the FastAPI UI backend.
# Similar to run-mcp.ps1, this script provides a single entry point for local UI backend startup.
#
# The prefab-based frontend dashboard (prefab_dashboard.py and friends) was
# removed - it was dead code for a UI approach superseded by SolidWorks-as-Code.
# This script now launches only the FastAPI backend (solidworks_mcp.ui.server:app),
# which several other things (session_service.py, checkpoint_service.py, the
# dashboard API, etc.) still depend on independent of any particular frontend.
#
# Usage:
#   .\run-ui.ps1
#   .\run-ui.ps1 -BackendPort 8766
#   .\run-ui.ps1 -NoNewWindow
#   .\run-ui.ps1 -DryRun

param(
    [int]$BackendPort = 8766,
    [switch]$NoNewWindow,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$srcPath = Join-Path $scriptDir "src"
$uiLogDir = Join-Path $scriptDir ".solidworks_mcp\ui_logs"
$backendLog = Join-Path $uiLogDir "fastapi_server.log"

function Get-PortOwners {
    param([int]$Port)

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        return @()
    }

    $owners = @()
    foreach ($connection in ($connections | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $process = Get-Process -Id $connection -ErrorAction SilentlyContinue
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $connection" -ErrorAction SilentlyContinue
        $owners += [PSCustomObject]@{
            Port = $Port
            Pid = $connection
            Name = if ($process) { $process.ProcessName } else { "<unknown>" }
            Path = if ($process) { $process.Path } else { $null }
            CommandLine = if ($cim) { $cim.CommandLine } else { $null }
        }
    }

    return $owners
}

function Test-IsRepoUiProcess {
    param([object]$Owner)

    $commandLine = [string]($Owner.CommandLine)
    $path = [string]($Owner.Path)
    $name = [string]($Owner.Name)

    if ([string]::IsNullOrWhiteSpace($commandLine) -and [string]::IsNullOrWhiteSpace($path)) {
        return $true
    }

    if ($name -in @("python", "pythonw", "pwsh", "powershell", "<unknown>")) {
        return $true
    }

    $repoHints = @(
        $scriptDir,
        "solidworks_mcp.ui.server:app",
        "run-ui.ps1"
    )

    foreach ($hint in $repoHints) {
        if ($commandLine -like "*$hint*" -or $path -like "*$hint*") {
            return $true
        }
    }

    return $false
}

function Resolve-UiPorts {
    param([int[]]$Ports)

    foreach ($port in $Ports) {
        $owners = @(Get-PortOwners -Port $port)
        if (-not $owners.Count) {
            continue
        }

        $foreignOwners = @($owners | Where-Object { -not (Test-IsRepoUiProcess $_) })
        if ($foreignOwners.Count) {
            $details = $foreignOwners | ForEach-Object {
                "PID=$($_.Pid) Name=$($_.Name) Command=$($_.CommandLine)"
            }
            Write-Error (
                "Port $port is already in use by a non-dashboard process.`n" +
                ($details -join "`n") +
                "`nStop that process or launch with a different port."
            )
            exit 1
        }

        foreach ($owner in $owners) {
            try {
                Stop-Process -Id $owner.Pid -Force -ErrorAction Stop
                Write-Host "Stopped stale UI process on port $port (PID $($owner.Pid), $($owner.Name))." -ForegroundColor Yellow
            } catch {
                if ($_.Exception.Message -like "*Cannot find a process with the process identifier*") {
                    Write-Host "Stale UI process PID $($owner.Pid) on port $port had already exited." -ForegroundColor Yellow
                    continue
                }
                Write-Error "Failed to stop stale UI process PID $($owner.Pid) on port ${port}: $_"
                exit 1
            }
        }
    }
}

if (-not (Test-Path $uiLogDir)) {
    New-Item -ItemType Directory -Path $uiLogDir -Force | Out-Null
}

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error (
        "Virtual environment python not found: $venvPython`n" +
        "Run one of:`n" +
        "  .\dev-commands.ps1 dev-install`n" +
        "  .\dev-commands.ps1 dev-install-uv"
    )
    exit 1
}

$pipCheck = & $venvPython -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip missing in .venv - bootstrapping with ensurepip..." -ForegroundColor Yellow
    & $venvPython -m ensurepip --upgrade
}

Resolve-UiPorts -Ports @($BackendPort)

$backendCmd = "`"$venvPython`" -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port $BackendPort --reload --reload-dir src"
$backendShellCommand = "Set-Location -LiteralPath '$scriptDir'; `$env:PYTHONPATH='$srcPath'; & '$venvPython' -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port $BackendPort --reload --reload-dir src 2>&1 | Tee-Object -FilePath '$backendLog' -Append"

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

Write-Host "Starting SolidWorks UI backend" -ForegroundColor Cyan
Write-Host "- Backend : http://127.0.0.1:$BackendPort" -ForegroundColor Yellow
Write-Host "- OpenAPI : http://127.0.0.1:$BackendPort/docs" -ForegroundColor Yellow
Write-Host "- Logs    : $backendLog" -ForegroundColor Yellow
Write-Host ""

if ($DryRun) {
    Write-Host "Dry run enabled. Command:" -ForegroundColor Green
    Write-Host "Backend : $backendCmd"
    exit 0
}

if ($NoNewWindow) {
    Write-Host "Running backend in a background job in this shell..." -ForegroundColor Cyan

    Start-Job -Name "solidworks-ui-backend" -ScriptBlock {
        param($workingDir, $pythonExe, $argsArray, $pythonPath, $backendLogPath)
        Set-Location $workingDir
        $env:PYTHONPATH = $pythonPath
        & $pythonExe @argsArray *>> $backendLogPath
    } -ArgumentList $scriptDir, $venvPython, $backendArgs, $srcPath, $backendLog | Out-Null

    Write-Host "Started job: solidworks-ui-backend" -ForegroundColor Green
    Write-Host "Use Get-Job / Receive-Job / Stop-Job to monitor and stop." -ForegroundColor Yellow
    exit 0
}

Write-Host "Launching a PowerShell window..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $backendShellCommand
)

Write-Host "UI backend launch requested." -ForegroundColor Green
