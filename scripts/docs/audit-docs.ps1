$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$buildScript = Join-Path $PSScriptRoot "build-docs.ps1"
$outDir = Join-Path $repoRoot ".generated\docs"

if (-not (Test-Path $buildScript)) {
    Write-Host "ERROR: Missing build script at $buildScript" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$verboseLog = Join-Path $outDir "mkdocs-build-$timestamp.log"
$strictLog = Join-Path $outDir "mkdocs-strict-$timestamp.log"
$reportPath = Join-Path $outDir "docs-audit-$timestamp.md"
$latestPath = Join-Path $outDir "docs-audit-latest.md"

Write-Host "[1/3] Running verbose docs build..." -ForegroundColor Cyan
& $buildScript -VerboseOutput *>&1 | Tee-Object -FilePath $verboseLog | Out-Null
$verboseCode = $LASTEXITCODE

Write-Host "[2/3] Running strict docs build..." -ForegroundColor Cyan
& $buildScript -Strict *>&1 | Tee-Object -FilePath $strictLog | Out-Null
$strictCode = $LASTEXITCODE

$warningLines = @()
if (Test-Path $strictLog) {
    $warningLines = Select-String -Path $strictLog -Pattern "^WARNING\s-\s" | ForEach-Object { $_.Line }
}

$errorLines = @()
if (Test-Path $strictLog) {
    $errorLines = Select-String -Path $strictLog -Pattern "Traceback|UnicodeEncodeError|^ERROR\s-\s|Aborted with" | ForEach-Object { $_.Line }
}

$navWarnings = ($warningLines | Where-Object { $_ -match 'not included in the "nav" configuration' }).Count
$griffeWarnings = ($warningLines | Where-Object { $_ -match "griffe:" }).Count
$linkWarnings = ($warningLines | Where-Object { $_ -match "contains a link" }).Count
$autorefWarnings = ($warningLines | Where-Object { $_ -match "mkdocs_autorefs:" }).Count
$otherWarnings = $warningLines.Count - $navWarnings - $griffeWarnings - $linkWarnings - $autorefWarnings

$report = @(
    "# Docs Audit Report",
    "",
    "- Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "- Verbose build exit code: $verboseCode",
    "- Strict build exit code: $strictCode",
    "- Verbose log: $verboseLog",
    "- Strict log: $strictLog",
    "",
    "## Warning Summary (Strict Build)",
    "",
    "- Total warnings: $($warningLines.Count)",
    "- Nav omissions: $navWarnings",
    "- Griffe/mkdocstrings parse warnings: $griffeWarnings",
    "- Broken docs links: $linkWarnings",
    "- Autorefs cross-reference warnings: $autorefWarnings",
    "- Other warnings: $otherWarnings",
    "- Detected hard-error lines: $($errorLines.Count)",
    "",
    "## Raw Warning Lines",
    ""
)

if ($warningLines.Count -eq 0) {
    $report += "- None"
} else {
    foreach ($line in $warningLines) {
        $report += "- $line"
    }
}

$report += ""
$report += "## Raw Error Lines"
$report += ""
if ($errorLines.Count -eq 0) {
    $report += "- None"
} else {
    foreach ($line in $errorLines) {
        $report += "- $line"
    }
}

Set-Content -Path $reportPath -Value $report -Encoding UTF8
Set-Content -Path $latestPath -Value $report -Encoding UTF8

Write-Host "[3/3] Audit report written:" -ForegroundColor Green
Write-Host "  $reportPath" -ForegroundColor Green
Write-Host "  $latestPath" -ForegroundColor Green

if ($strictCode -ne 0) {
    Write-Host "Strict build reported warnings/errors. Review docs-audit-latest.md." -ForegroundColor Yellow
}

exit 0
