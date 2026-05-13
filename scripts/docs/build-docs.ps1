param(
    [switch]$Strict,
    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: .venv Python not found at $venvPython" -ForegroundColor Red
    Write-Host "Run .\\dev-commands.ps1 dev-install first." -ForegroundColor Yellow
    exit 1
}

$args = @("-m", "mkdocs", "build", "--clean")
if ($Strict) {
    $args += "--strict"
}
if ($VerboseOutput) {
    $args += "--verbose"
}

# Suppress third-party MkDocs 2 warning noise in scripted runs.
if (-not $env:DISABLE_MKDOCS_2_WARNING) {
    $env:DISABLE_MKDOCS_2_WARNING = "true"
}

Write-Host "Running: $venvPython $($args -join ' ')" -ForegroundColor Cyan
& $venvPython @args
exit $LASTEXITCODE
