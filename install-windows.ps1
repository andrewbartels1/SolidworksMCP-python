# SolidWorks MCP Server - Windows Installation Script
# This script automates the Windows setup process.

$ErrorActionPreference = "Stop"

function Step {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Green
}

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "SolidWorks MCP Server - Windows Installation" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan

Step "[1/6] Checking Python installation..."
$pythonExe = python -c "import sys; print(sys.executable)" 2>&1
if ($LASTEXITCODE -ne 0 -or -not $pythonExe) {
    Write-Host "ERROR: Python not found in PATH." -ForegroundColor Red
    Write-Host "Install Python 3.11+ from https://python.org and enable Add Python to PATH." -ForegroundColor Yellow
    exit 1
}
$pythonVersion = python --version 2>&1
Write-Host "Found $pythonVersion at $pythonExe" -ForegroundColor Green

Step "[2/6] Checking repository..."
if (-not (Test-Path "pyproject.toml")) {
    Write-Host "Repository not found in current folder. Cloning..." -ForegroundColor Yellow
    git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
    Set-Location SolidworksMCP-python
}
Write-Host "Repository ready at $(Get-Location)" -ForegroundColor Green

Step "[3/6] Creating virtual environment..."
if (Test-Path ".venv") {
    # Validate the existing venv has a pyvenv.cfg (it may be corrupted)
    if (-not (Test-Path ".venv\pyvenv.cfg")) {
        Write-Host "Existing .venv is missing pyvenv.cfg (corrupted). Recreating..." -ForegroundColor Yellow
        try { Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue } catch {}
        python -m venv .venv
        Write-Host "Recreated .venv" -ForegroundColor Green
    } else {
        Write-Host "Using existing .venv" -ForegroundColor Yellow
    }
} else {
    python -m venv .venv
    Write-Host "Created .venv" -ForegroundColor Green
}

Step "[4/6] Installing dependencies..."
$venvPython = Join-Path (Get-Location) ".venv\\Scripts\\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: venv python not found at $venvPython" -ForegroundColor Red
    exit 1
}

# Bootstrap pip if missing (can happen when venv is created from conda/micromamba Python)
$pipCheck = & $venvPython -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip not found in venv - bootstrapping with ensurepip..." -ForegroundColor Yellow
    & $venvPython -m ensurepip --upgrade
}

& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install -e ".[dev,test,docs,ui]"

# Verify prefab.exe was installed (pip occasionally skips console scripts on first install)
$venvPrefab = Join-Path (Get-Location) ".venv\Scripts\prefab.exe"
if (-not (Test-Path $venvPrefab)) {
    Write-Host "prefab.exe not found after install — force-reinstalling prefab-ui..." -ForegroundColor Yellow
    & $venvPython -m pip install --force-reinstall "prefab-ui>=0.19.0"
}
if (Test-Path $venvPrefab) {
    Write-Host "prefab.exe verified at $venvPrefab" -ForegroundColor Green
} else {
    Write-Host "WARNING: prefab.exe still missing. Run '.\run-ui.ps1' — it will fall back automatically." -ForegroundColor Yellow
}

Write-Host "Dependencies installed (including UI extras)." -ForegroundColor Green

Step "[5/6] Configuring VS Code MCP settings..."
$mcpJsonPath = Join-Path $env:APPDATA "Code\\User\\mcp.json"
if (Test-Path $mcpJsonPath) {
    $raw = Get-Content -Raw $mcpJsonPath
    $config = $raw | ConvertFrom-Json

    if (-not $config.servers) {
        $config | Add-Member -NotePropertyName servers -NotePropertyValue @{} -Force
    }

    $projectPath = (Get-Location).Path
    $serverConfig = [ordered]@{
        type = "stdio"
        command = "$venvPython"
        args = @("-m", "solidworks_mcp.server")
        cwd = "$projectPath"
    }

    # Convert PSCustomObject -> hashtable for safe assignment
    $serversHash = @{}
    foreach ($p in $config.servers.PSObject.Properties) {
        $serversHash[$p.Name] = $p.Value
    }
    $serversHash["solidworks-mcp-server"] = $serverConfig
    $config.servers = $serversHash

    $config | ConvertTo-Json -Depth 20 | Set-Content -Path $mcpJsonPath -Encoding UTF8
    Write-Host "Updated $mcpJsonPath" -ForegroundColor Green
} else {
    Write-Host "WARNING: mcp.json not found at $mcpJsonPath" -ForegroundColor Yellow
    Write-Host "Create it manually if needed." -ForegroundColor Yellow
}

Step "[6/6] Verifying installation..."
$testResult = & $venvPython -c "import solidworks_mcp; print('OK')" 2>&1
if ($LASTEXITCODE -ne 0 -or $testResult -notmatch "OK") {
    Write-Host "ERROR: Import test failed." -ForegroundColor Red
    Write-Host $testResult
    exit 1
}
Write-Host "Import test passed." -ForegroundColor Green

Write-Host "" 
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "Installation complete" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Start SolidWorks on this Windows machine."
Write-Host "2. Restart VS Code so MCP config reloads."
Write-Host "3. In VS Code, start server solidworks-mcp-server."
Write-Host ""
Write-Host "To start the SolidWorks UI dashboard:" -ForegroundColor Cyan
Write-Host "  .\dev-commands.ps1 dev-ui-probe   # Debug probe"
Write-Host "  .\run-ui.ps1                       # Full dashboard"
Write-Host ""
Write-Host "Manual MCP start command:" -ForegroundColor Cyan
Write-Host ".\\.venv\\Scripts\\python.exe -m solidworks_mcp.server"
