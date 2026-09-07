# SolidWorks MCP Python - Development Commands for PowerShell (Windows 11)
# Run individual commands: .\dev-commands.ps1 dev-test
# Or source and call directly: . .\dev-commands.ps1; dev-test

param(
    [string]$Command = ""
)

Write-Host "SolidWorks MCP Development Commands" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

function Get-VenvPython {
    return (Join-Path $PSScriptRoot ".venv\Scripts\python.exe")
}

function Resolve-UvCommand {
    $uvCommand = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCommand) {
        return $uvCommand.Source
    }

    $candidatePaths = @(Join-Path $HOME ".local\bin\uv.exe")
    if ($env:LOCALAPPDATA) {
        $candidatePaths += Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe"
    }

    foreach ($candidatePath in $candidatePaths) {
        if (Test-Path $candidatePath) {
            $candidateDir = Split-Path $candidatePath -Parent
            $pathParts = $env:Path -split ";"
            if ($pathParts -notcontains $candidateDir) {
                $env:Path = "$candidateDir;$env:Path"
            }
            return $candidatePath
        }
    }

    return $null
}

function Ensure-Venv {
    $venvDir = Join-Path $PSScriptRoot ".venv"
    $venvCfg = Join-Path $venvDir "pyvenv.cfg"
    $venvPy  = Get-VenvPython

    # Validate existing venv
    if ((Test-Path $venvPy) -and (Test-Path $venvCfg)) {
        & $venvPy -c "import sys, unicodedata; print(sys.version_info.major)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & $venvPy -m pip --version 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $true }
            Write-Host "Bootstrapping pip in existing .venv..." -ForegroundColor Yellow
            & $venvPy -m ensurepip --upgrade
            & $venvPy -m pip --version 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return $true }
        }
        Write-Host ".venv is broken; recreating..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $venvDir -ErrorAction SilentlyContinue
    }

    # Create with uv (preferred)
    $uvCmd = Resolve-UvCommand
    if ($uvCmd) {
        Write-Host "Creating .venv with uv..." -ForegroundColor Cyan
        & $uvCmd venv .venv --python 3.13
        if ($LASTEXITCODE -eq 0 -and (Test-Path $venvPy)) {
            & $venvPy -m ensurepip --upgrade
            return $true
        }
    }

    # Fallback: py launcher or python
    $pyCmd  = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
    $pyArgs = if ($pyCmd -eq "py") { @("-3.13") } else { @() }
    Write-Host "Creating .venv with $pyCmd..." -ForegroundColor Cyan
    & $pyCmd @pyArgs -m venv .venv
    if ($LASTEXITCODE -eq 0 -and (Test-Path $venvPy)) {
        & $venvPy -m ensurepip --upgrade
        & $venvPy -m pip install --upgrade pip setuptools wheel | Out-Null
        return $true
    }

    Write-Host "ERROR: Failed to create .venv. Install uv: https://docs.astral.sh/uv/" -ForegroundColor Red
    return $false
}

function Invoke-Venv {
    param([Parameter(Mandatory = $true)][string[]]$Args)
    $venvPy = Get-VenvPython
    if (-not (Test-Path $venvPy)) {
        Write-Host "ERROR: .venv not found. Run: .\dev-commands.ps1 dev-install" -ForegroundColor Red
        $global:LASTEXITCODE = 1
        return
    }
    & $venvPy @Args
}

function Invoke-Pytest {
    param([Parameter(Mandatory = $true)][string[]]$Args)
    Invoke-Venv -Args (@("-m", "pytest") + $Args)
}

function Invoke-IntegrationCleanup {
    Invoke-Venv @("tests/scripts/cleanup_generated_integration_artifacts.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Generated-artifact cleanup failed (non-blocking)." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

function dev-help {
    Write-Host "Available Commands:" -ForegroundColor Green
    Write-Host ""
    Write-Host "  dev-install         Install/sync dependencies via uv (creates/repairs .venv)"
    Write-Host "  dev-install-ui      Install/repair UI extras in .venv only"
    Write-Host "  dev-test            Run test suite with coverage (excludes solidworks_only, smoke, slow)"
    Write-Host "  dev-test-full       Run full suite including real SolidWorks integration tests"
    Write-Host "  dev-test-combined   Mock (parallel) + real-SW (serial, drain+idle between each test), merged into one true coverage report"
    Write-Host "  dev-lint            Format + lint code (ruff format + ruff check)"
    Write-Host "  dev-check-tool-count  Verify 'N tools' claims across docs match the real AST-counted total"
    Write-Host "  dev-format          Format code only (ruff format)"
    Write-Host "  dev-build           Build package for distribution"
    Write-Host "  dev-run             Start the MCP server"
    Write-Host "  dev-ui              Start the FastAPI UI backend"
    Write-Host "  dev-docs-build      Build documentation once (mkdocs build --clean)"
    Write-Host "  dev-docs-strict     Build documentation in strict mode"
    Write-Host "  dev-docs-audit      Run verbose + strict docs audit and write summary"
    Write-Host "  dev-docs            Build and serve documentation (http://localhost:8000)"
    Write-Host "  dev-docs-discovery  Index SolidWorks COM/VBA documentation (Windows + SW running)"
    Write-Host "  dev-clean           Remove build/cache artifacts"
    Write-Host ""
}

function dev-install {
    Write-Host "Installing SolidWorks MCP Server..." -ForegroundColor Cyan

    $uvCmd = Resolve-UvCommand
    if (-not $uvCmd) {
        Write-Host "ERROR: uv is required. Install from: https://docs.astral.sh/uv/" -ForegroundColor Red
        Write-Host "Hint: installer location is usually $HOME\.local\bin\uv.exe" -ForegroundColor Yellow
        return
    }

    $ready = Ensure-Venv
    if (-not $ready) { return }

    $venvPy = Get-VenvPython
    & $uvCmd pip install --python $venvPy -e ".[dev,test,docs,ui,rag]"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Installation complete!" -ForegroundColor Green
    } else {
        Write-Host "Installation failed." -ForegroundColor Red
    }
}

function dev-install-ui {
    Write-Host "Installing/repairing UI extras in .venv..." -ForegroundColor Cyan
    $ready = Ensure-Venv
    if (-not $ready) { return }

    $venvPy = Get-VenvPython
    & $venvPy -m pip install "fastapi>=0.115.0" "uvicorn>=0.24.0" -q
    if ($LASTEXITCODE -eq 0) {
        Write-Host "UI extras installed." -ForegroundColor Green
    } else {
        Write-Host "Failed to install UI extras." -ForegroundColor Red
    }
}

function dev-test {
    Write-Host "Running tests with coverage..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"

    # Keep generated integration artifacts from previous runs from accumulating.
    Invoke-IntegrationCleanup

    # -n 8, not "auto": this machine has 24 logical CPUs but only ~10GB free
    # RAM once VSCode + SolidWorks are running - "auto" spawns a worker per
    # CPU, each loading the full package + deps, and OOMs the machine. 8 is a
    # deliberate middle ground: noticeably faster than 4, still well clear of
    # the OOM ceiling.
    Invoke-Pytest @(
        "tests/",
        "-m", "not solidworks_only and not smoke and not slow",
        "-n", "8",
        "--cov=src/solidworks_mcp",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--durations=10",
        "-v"
    )

    Invoke-IntegrationCleanup

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Tests passed! Coverage: htmlcov/index.html" -ForegroundColor Green
    } else {
        Write-Host "Tests failed." -ForegroundColor Red
    }
}

function dev-test-full {
    Write-Host "Running full test suite (including real SolidWorks integration)..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
    $env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION = "true"
    Invoke-Pytest @(
        "tests/",
        "-n", "1",
        "--cov=src/solidworks_mcp",
        "--cov-config=.coveragerc.full",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
        "--cov-fail-under=99",
        "--durations=10",
        "-v"
    )

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Full tests passed!" -ForegroundColor Green
    } else {
        Write-Host "Full tests failed." -ForegroundColor Red
    }
}

function dev-test-combined {
    # dev-test-full runs everything serially in one ~30-50min pytest session
    # (-n 1 for the whole tree, since real COM needs single-threaded). This
    # runs the mock suite in parallel, then the real-SolidWorks suite in small
    # serial batches, with EVERY pytest invocation --cov-append-ing into one
    # shared data file (.coverage.combined). The result is the union of what
    # mock tests AND real-SolidWorks tests each cover - no separate mock/real
    # files, no `coverage combine` of named files (that step is what silently
    # dropped the mock half before: "Combined 1 file").
    #
    # Why the union matters: a line only reachable via real COM (e.g. a
    # defensive "SolidWorks returned nothing" raise inside add_mate) always
    # shows as "missing" in a mock-only report, even once
    # test_live_sw_regression.py genuinely exercises it. Combined coverage
    # answers "is this covered by ANY test", so new tests only get written for
    # lines neither suite reaches.
    #
    # The real-SolidWorks phase is ONE serial pytest session (-n 1) with a
    # few seconds' idle between each test (SW_TEST_PACE_SECONDS, default 4).
    # It drains open documents + idles between each test - the recovery the
    # per-batch drain gave, without the per-batch subprocess churn.
    Write-Host "Running combined coverage: mock suite (parallel) + real SolidWorks suite (serial, paced), one appended report..." -ForegroundColor Cyan
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"

    # Wipe prior coverage data - .coverage, .coverage.<anything>, and any
    # leftover xdist fragments - but never .coveragerc / .coveragerc.full.
    Get-ChildItem -Path . -Force -File -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -eq ".coverage" -or
            ($_.Name -like ".coverage.*" -and $_.Name -notlike ".coveragerc*")
        } | Remove-Item -Force -ErrorAction SilentlyContinue
    Remove-Item -Path htmlcov, coverage.xml -Recurse -Force -ErrorAction SilentlyContinue

    # Every phase appends into this one file.
    $env:COVERAGE_FILE = ".coverage.combined"
    $covBase = @("--cov=src/solidworks_mcp", "--cov-append", "--cov-report=", "--cov-fail-under=0")

    # -n 8, not "auto": this machine has 24 logical CPUs but only ~10GB free
    # RAM once VSCode + SolidWorks are running, and "auto" spawns a worker
    # per CPU - each loading the full package + deps. Already learned the
    # hard way once this session (see TODO_SESSION.md's 2026-08-14 entry) -
    # "auto" OOM'd the machine again when this command first ran. 8 is a
    # deliberate middle ground: faster than 4, still well clear of the ceiling.
    Write-Host "Phase 1/3: mock suite (parallel, -n 8)..." -ForegroundColor Cyan
    Invoke-Pytest (@("tests/", "-m", "not solidworks_only", "-n", "8", "-q") + $covBase)
    $mockExit = $LASTEXITCODE
    if (Test-Path .coverage.combined) {
        Write-Host ("  mock coverage recorded ({0:N0} bytes)" -f (Get-Item .coverage.combined).Length) -ForegroundColor DarkGray
    } else {
        Write-Host "  WARNING: no .coverage.combined after Phase 1 - the mock half will be missing from the report." -ForegroundColor Yellow
    }

    #   SW_TEST_PACE_SECONDS  idle seconds after each real test (default 4)
    #   SW_TEST_HEADLESS=1    hide the SW window for the real suite - ~40%
    #                        faster, but its sketch COM goes flaky hidden
    #                        (a couple of wave3 tests will flake); off by default
    $pace = if ($env:SW_TEST_PACE_SECONDS) { $env:SW_TEST_PACE_SECONDS } else { "4" }

    # A SOLIDWORKS_MCP_HEADLESS left in the shell from an earlier experiment
    # would silently flake the run - decide it explicitly from SW_TEST_HEADLESS.
    if ($env:SW_TEST_HEADLESS -and $env:SW_TEST_HEADLESS -ne "0") {
        $env:SOLIDWORKS_MCP_HEADLESS = "1"
        Write-Host "  SW_TEST_HEADLESS set - running the real suite with the SolidWorks window hidden (expect a few flakes)." -ForegroundColor Yellow
    } else {
        Remove-Item Env:\SOLIDWORKS_MCP_HEADLESS -ErrorAction SilentlyContinue
    }

    Write-Host "Phase 2/3: real SolidWorks suite (serial, ${pace}s between tests - requires SolidWorks running)..." -ForegroundColor Cyan
    $env:SOLIDWORKS_MCP_RUN_REAL_INTEGRATION = "true"
    $env:SW_TEST_PACE_SECONDS = "$pace"
    $realExit = 0

    Write-Host "  preflight: draining any open documents..." -ForegroundColor DarkGray
    Invoke-Venv @("tests/scripts/sw_close_all_and_settle.py", "--settle", "2")
    if ($LASTEXITCODE -eq 2) {
        Write-Host "  SolidWorks is not reachable - skipping the real suite. Start SolidWorks and re-run." -ForegroundColor Red
        $realExit = 2
    } else {
        Invoke-Pytest (@("tests/", "-m", "solidworks_only", "-n", "1", "-q", "--timeout=300") + $covBase)
        $realExit = $LASTEXITCODE
    }
    Remove-Item Env:\COVERAGE_FILE -ErrorAction SilentlyContinue

    Write-Host "Phase 3/3: coverage report (.coverage.combined = mock + real, appended)..." -ForegroundColor Cyan
    # Fold in any xdist fragments an interrupted batch left behind; harmless no-op otherwise.
    $frags = @(Get-ChildItem -Path . -Force -File -Filter ".coverage.combined.*" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
    if ($frags.Count -gt 0) {
        Invoke-Venv (@("-m", "coverage", "combine", "--data-file=.coverage.combined", "--append") + $frags)
    }
    if (-not (Test-Path .coverage.combined)) {
        Write-Host "  ERROR: .coverage.combined does not exist - no coverage was recorded by either phase." -ForegroundColor Red
        $reportExit = 1
    } else {
        Invoke-Venv @("-m", "coverage", "html", "--data-file=.coverage.combined", "-d", "htmlcov")
        Invoke-Venv @("-m", "coverage", "xml", "--data-file=.coverage.combined", "-o", "coverage.xml")
        Invoke-Venv @("-m", "coverage", "report", "--data-file=.coverage.combined", "-m", "--fail-under=99")
        $reportExit = $LASTEXITCODE
    }

    if ($mockExit -eq 0 -and $realExit -eq 0 -and $reportExit -eq 0) {
        Write-Host "Combined suite passed! True combined coverage written to htmlcov/index.html" -ForegroundColor Green
    } else {
        Write-Host "Combined suite failed (mock exit=$mockExit, real exit=$realExit, coverage gate exit=$reportExit)." -ForegroundColor Red
        if ($realExit -eq 2) { Write-Host "  real exit=2: SolidWorks was not running - start it and re-run." -ForegroundColor Yellow }
        if ($realExit -gt 0 -and $realExit -ne 2) { Write-Host "  real tests failed - if flaky COM errors, restart SolidWorks and/or raise SW_TEST_PACE_SECONDS." -ForegroundColor Yellow }
    }
}

function dev-lint {
    Write-Host "Formatting and linting..." -ForegroundColor Cyan
    Invoke-Venv @("-m", "ruff", "format", "src/", "tests/")
    if ($LASTEXITCODE -ne 0) { Write-Host "Formatting failed." -ForegroundColor Red; return }

    Invoke-Venv @("-m", "ruff", "check", "src/", "tests/")
    if ($LASTEXITCODE -eq 0) { Write-Host "Format + lint passed!" -ForegroundColor Green }
    else { Write-Host "Lint issues found." -ForegroundColor Yellow }
}

function dev-check-tool-count {
    Write-Host "Checking tool-count consistency across docs..." -ForegroundColor Cyan
    Invoke-Venv @("src/utils/check_tool_docs_consistency.py", "--category")
    if ($LASTEXITCODE -eq 0) { Write-Host "All tool-count references are consistent." -ForegroundColor Green }
    else {
        Write-Host "Tool-count drift found. Re-run with --fix for the auto-fixable ones:" -ForegroundColor Yellow
        Write-Host "  .venv\Scripts\python.exe src/utils/check_tool_docs_consistency.py --fix" -ForegroundColor Yellow
    }
}

function dev-format {
    Write-Host "Formatting code..." -ForegroundColor Cyan
    Invoke-Venv @("-m", "ruff", "format", "src/", "tests/")
    if ($LASTEXITCODE -eq 0) { Write-Host "Format complete." -ForegroundColor Green }
    else { Write-Host "Formatting failed." -ForegroundColor Red }
}

function dev-build {
    Write-Host "Building package..." -ForegroundColor Cyan
    Invoke-Venv @("-m", "build")
    if ($LASTEXITCODE -eq 0) { Write-Host "Build complete! dist/" -ForegroundColor Green }
    else { Write-Host "Build failed." -ForegroundColor Red }
}

function dev-run {
    Write-Host "Starting MCP server..." -ForegroundColor Cyan
    Invoke-Venv @("-m", "solidworks_mcp.server")
}

function dev-ui {
    # The prefab-based frontend dashboard was removed (dead code for a UI
    # approach superseded by SolidWorks-as-Code). This starts just the
    # FastAPI backend (solidworks_mcp.ui.server:app) - still real,
    # independent infrastructure other things build on.
    Write-Host "Starting UI backend (FastAPI)..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "run-ui.ps1")
}

function dev-docs {
    Write-Host "Building docs..." -ForegroundColor Cyan
    Invoke-Venv @("-m", "mkdocs", "build", "--clean")
    if ($LASTEXITCODE -ne 0) { Write-Host "Docs build failed." -ForegroundColor Red; return }
    Write-Host "Serving at http://localhost:8000 (Ctrl+C to stop)..." -ForegroundColor Yellow
    Invoke-Venv @("-m", "mkdocs", "serve", "--dev-addr=localhost:8000")
}

function dev-docs-build {
    Write-Host "Building docs..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "scripts\docs\build-docs.ps1")
    if ($LASTEXITCODE -eq 0) { Write-Host "Docs build passed." -ForegroundColor Green }
    else { Write-Host "Docs build failed." -ForegroundColor Red }
}

function dev-docs-strict {
    Write-Host "Building docs in strict mode..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "scripts\docs\build-docs.ps1") -Strict
    if ($LASTEXITCODE -eq 0) { Write-Host "Strict docs build passed." -ForegroundColor Green }
    else { Write-Host "Strict docs build reported warnings/errors." -ForegroundColor Yellow }
}

function dev-docs-audit {
    Write-Host "Running docs audit (verbose + strict)..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "scripts\docs\audit-docs.ps1")
    if ($LASTEXITCODE -eq 0) { Write-Host "Docs audit completed." -ForegroundColor Green }
    else { Write-Host "Docs audit failed." -ForegroundColor Red }
}

function dev-docs-discovery {
    Write-Host "Indexing SolidWorks COM and VBA documentation..." -ForegroundColor Cyan
    # $IsWindows and PSVersionTable.Platform only exist in PS 6+; PS 5.1 is Windows-exclusive so treat missing Platform as Windows
    $isWindowsOS = $IsWindows -or ($PSVersionTable.Platform -eq "Win32NT") -or ($null -eq $PSVersionTable.Platform)
    if (-not $isWindowsOS) {
        Write-Host "ERROR: Windows only." -ForegroundColor Red
        return
    }
    $swProcess = Get-Process | Where-Object { $_.ProcessName -like "*sldworks*" }
    if (-not $swProcess) {
        Write-Host "WARNING: SolidWorks not running. Start it and retry." -ForegroundColor Yellow
        return
    }
    $env:PY_KEY_VALUE_DISABLE_BEARTYPE = "true"
    $repoRoot = $PSScriptRoot.Replace("'", "''")
    $pythonCode = @"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(r'$repoRoot') / 'src'))
from solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery
d = SolidWorksDocsDiscovery()
d.discover_all()
f = d.save_index()
s = d.create_search_summary()
print('COM Objects:', s.get('total_com_objects'), ' Methods:', s.get('total_methods'), ' Index:', f)
"@
    Invoke-Venv -Args @("-c", $pythonCode)
    if ($LASTEXITCODE -eq 0) { Write-Host "Discovery complete." -ForegroundColor Green }
    else { Write-Host "Discovery failed." -ForegroundColor Red }
}

function dev-clean {
    Write-Host "Cleaning build artifacts..." -ForegroundColor Cyan
    @("build", "dist", "htmlcov", ".pytest_cache", ".mypy_cache", "site", "*.egg-info") | ForEach-Object {
        Get-ChildItem -Path . -Filter $_ -Recurse -Directory -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -Path .coverage, coverage.xml -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Filter "*.egg-info" -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Filter "__pycache__"  -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path . -Filter "*.pyc"         -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Clean complete!" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

if ([string]::IsNullOrWhiteSpace($Command) -or $Command -eq "dev-help") {
    dev-help
} elseif (Get-Command -Name $Command -CommandType Function -ErrorAction SilentlyContinue) {
    & $Command
} else {
    Write-Host "Unknown command: $Command" -ForegroundColor Red
    dev-help
    exit 1
}
