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
docker run --rm -t $imageName
if ($LASTEXITCODE -ne 0) {
    Write-Error "Local CI container run failed."
}

Write-Host "Local CI run completed successfully." -ForegroundColor Green
