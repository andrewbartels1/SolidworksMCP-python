param(
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker CLI not found. Install Docker Desktop first."
}

# BuildKit is required for --mount=type=cache in the Dockerfile.
$env:DOCKER_BUILDKIT = "1"

$imageName = "solidworks-mcp-ci-local"

if (-not $NoBuild) {
    Write-Host "Building local CI image ($imageName)..." -ForegroundColor Cyan
    docker build -f .ci/Dockerfile -t $imageName .
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker build failed."
    }
}

Write-Host "Running local CI test command (make test)..." -ForegroundColor Cyan
$ghToken = if ($env:GH_TOKEN) {
    $env:GH_TOKEN
} elseif ($env:GITHUB_API_KEY) {
    $env:GITHUB_API_KEY
} else {
    "local-ci-placeholder-token"
}

$githubApiKey = if ($env:GITHUB_API_KEY) {
    $env:GITHUB_API_KEY
} else {
    $ghToken
}

if (-not $env:GH_TOKEN -and -not $env:GITHUB_API_KEY) {
    Write-Host "GH_TOKEN/GITHUB_API_KEY not set; using placeholder values for local CI-only test paths." -ForegroundColor Yellow
}

docker run --rm -t `
    -e "GH_TOKEN=$ghToken" `
    -e "GITHUB_API_KEY=$githubApiKey" `
    $imageName
if ($LASTEXITCODE -ne 0) {
    Write-Error "Local CI container run failed."
}

Write-Host "Local CI run completed successfully." -ForegroundColor Green
