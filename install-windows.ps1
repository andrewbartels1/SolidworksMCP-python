# SolidWorks MCP Server - Windows Installation Script
# This script automates the Windows setup process.

$ErrorActionPreference = "Stop"

function Step {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Green
}

function Test-PythonLauncher {
    param([string[]]$Launcher)

    try {
        if ($Launcher.Count -gt 1) {
            $probe = & $Launcher[0] @($Launcher[1..($Launcher.Count - 1)] + @("-c", "import sys; print(sys.executable)")) 2>&1
        } else {
            $probe = & $Launcher[0] -c "import sys; print(sys.executable)" 2>&1
        }

        if ($LASTEXITCODE -ne 0) {
            return $null
        }

        $exe = ($probe | Select-Object -Last 1).ToString().Trim()
        if (-not $exe -or -not (Test-Path $exe)) {
            return $null
        }

        return $exe
    } catch {
        return $null
    }
}

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)

    if ($script:pythonLauncher.Count -gt 1) {
        & $script:pythonLauncher[0] @($script:pythonLauncher[1..($script:pythonLauncher.Count - 1)] + $Args)
    } else {
        & $script:pythonLauncher[0] @Args
    }
}

function Remove-JsonComments {
    param([string]$Text)

    if (-not $Text) {
        return ""
    }

    $sb = New-Object System.Text.StringBuilder
    $inString = $false
    $escape = $false
    $inLineComment = $false
    $inBlockComment = $false

    for ($i = 0; $i -lt $Text.Length; $i++) {
        $ch = $Text[$i]
        $next = if ($i + 1 -lt $Text.Length) { $Text[$i + 1] } else { [char]0 }

        if ($inLineComment) {
            if ($ch -eq "`n") {
                $inLineComment = $false
                [void]$sb.Append($ch)
            }
            continue
        }

        if ($inBlockComment) {
            if ($ch -eq "*" -and $next -eq "/") {
                $inBlockComment = $false
                $i++
            }
            continue
        }

        if ($inString) {
            [void]$sb.Append($ch)
            if ($escape) {
                $escape = $false
                continue
            }
            if ($ch -eq "\\") {
                $escape = $true
                continue
            }
            if ($ch -eq '"') {
                $inString = $false
            }
            continue
        }

        if ($ch -eq '"') {
            $inString = $true
            [void]$sb.Append($ch)
            continue
        }

        if ($ch -eq "/" -and $next -eq "/") {
            $inLineComment = $true
            $i++
            continue
        }

        if ($ch -eq "/" -and $next -eq "*") {
            $inBlockComment = $true
            $i++
            continue
        }

        [void]$sb.Append($ch)
    }

    return $sb.ToString()
}

function Invoke-Uv {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & uv @Args
}

function Recreate-Venv {
    Write-Host "Recreating .venv..." -ForegroundColor Yellow
    try { Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue } catch {}
    if ($script:useUv) {
        Invoke-Uv venv .venv --python $script:pythonExe
    } else {
        Invoke-Python -m venv .venv
    }
    Write-Host "Recreated .venv" -ForegroundColor Green
}

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "SolidWorks MCP Server - Windows Installation" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan

Step "[1/6] Checking Python installation..."
$launcherCandidates = @(
    @{ Name = "python"; Cmd = @("python") },
    @{ Name = "py -3"; Cmd = @("py", "-3") },
    @{ Name = "py"; Cmd = @("py") }
)

$wherePython = @(where.exe python 2>$null | Where-Object {
    $_ -and $_ -notmatch "WindowsApps" -and $_ -notmatch "\\AppData\\Local\\Python\\bin\\"
})
foreach ($path in $wherePython) {
    $trimmed = $path.Trim()
    if ($trimmed) {
        $launcherCandidates += @{ Name = $trimmed; Cmd = @($trimmed) }
    }
}

$pythonExe = $null
$script:pythonExe = $null
$script:pythonLauncher = @("python")
foreach ($candidate in $launcherCandidates) {
    $resolved = Test-PythonLauncher -Launcher $candidate.Cmd
    if ($resolved) {
        $script:pythonLauncher = $candidate.Cmd
        $pythonExe = $resolved
        $script:pythonExe = $resolved
        break
    }
}

if (-not $pythonExe) {
    Write-Host "ERROR: No working Python launcher found." -ForegroundColor Red
    Write-Host "Install Python 3.11+ from https://python.org and ensure either 'python' or 'py -3' works." -ForegroundColor Yellow
    exit 1
}
$pythonVersion = Invoke-Python --version 2>&1
$versionText = ($pythonVersion | Select-Object -Last 1).ToString().Trim()
$versionMatch = [regex]::Match($versionText, "Python\s+(\d+)\.(\d+)")
if (-not $versionMatch.Success) {
    Write-Host "ERROR: Could not parse Python version from '$versionText'." -ForegroundColor Red
    exit 1
}

$major = [int]$versionMatch.Groups[1].Value
$minor = [int]$versionMatch.Groups[2].Value
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
    Write-Host "ERROR: Python 3.11+ is required. Found $versionText" -ForegroundColor Red
    exit 1
}

Write-Host "Found $pythonVersion at $pythonExe" -ForegroundColor Green

$script:useUv = $false
try {
    $null = & uv --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        $script:useUv = $true
        Write-Host "uv detected; using uv for virtualenv and package installation." -ForegroundColor Green
    } else {
        Write-Host "uv not detected; using pip workflow." -ForegroundColor Yellow
    }
} catch {
    Write-Host "uv not detected; using pip workflow." -ForegroundColor Yellow
}

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
        Recreate-Venv
    } else {
        $existingVenvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"
        if (-not (Test-Path $existingVenvPython) -or -not (Test-PythonLauncher -Launcher @($existingVenvPython))) {
            Write-Host "Existing .venv python is not usable. Recreating..." -ForegroundColor Yellow
            Recreate-Venv
        } else {
            Write-Host "Using existing .venv" -ForegroundColor Yellow
        }
    }
} else {
    if ($script:useUv) {
        Invoke-Uv venv .venv --python $script:pythonExe
    } else {
        Invoke-Python -m venv .venv
    }
    Write-Host "Created .venv" -ForegroundColor Green
}

Step "[4/6] Installing dependencies..."
$venvPython = Join-Path (Get-Location) ".venv\\Scripts\\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: venv python not found at $venvPython" -ForegroundColor Red
    exit 1
}

if (-not (Test-PythonLauncher -Launcher @($venvPython))) {
    Write-Host "venv python is not executable. Recreating venv..." -ForegroundColor Yellow
    Recreate-Venv
    $venvPython = Join-Path (Get-Location) ".venv\\Scripts\\python.exe"
    if (-not (Test-Path $venvPython) -or -not (Test-PythonLauncher -Launcher @($venvPython))) {
        Write-Host "ERROR: venv python is still not usable after recreation." -ForegroundColor Red
        exit 1
    }
}

& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install -e ".[dev,test,docs,ui,rag]"

# Verify prefab.exe was installed (pip occasionally skips console scripts on first install)
$venvPrefab = Join-Path (Get-Location) ".venv\Scripts\prefab.exe"
if (-not (Test-Path $venvPrefab)) {
    Write-Host "prefab.exe not found after install — force-reinstalling prefab-ui..." -ForegroundColor Yellow
    if ($script:useUv) {
        Invoke-Uv pip install --python $venvPython --force-reinstall "prefab-ui>=0.19.0"
    } else {
        & $venvPython -m pip install --force-reinstall "prefab-ui>=0.19.0"
    }
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
    $jsonForParse = Remove-JsonComments -Text $raw
    $config = $jsonForParse | ConvertFrom-Json

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
