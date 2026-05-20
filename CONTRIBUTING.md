# Contributing to SolidWorks MCP Server

Thanks for contributing.

This repository is Python-first and centered on SolidWorks MCP tooling plus optional agent/prompt-testing workflows.

## Development Process

1. Fork the repo and create a branch from `main`.
2. Make focused changes with tests/docs updates where relevant.
3. Run lint/tests/docs build locally.
4. **Run the local CI check** (see below) and confirm it passes before opening a PR.
5. Open a pull request with a concise summary.

## Local Setup

```powershell
git clone https://github.com/<your-username>/SolidworksMCP-python.git
cd SolidworksMCP-python

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs]"
```

## Local CI Check (required before PRs)

Before opening a pull request, run the local CI script to reproduce the same test environment used in GitHub Actions:

```powershell
.\run-ci-local.ps1
```

This builds a Docker image from `.ci/Dockerfile` and runs `make test` inside it — the exact command GitHub CI executes. A clean pass here means your PR will not fail CI on test issues.

If Docker is not available, run the full local test suite instead and confirm it passes:

```powershell
.\dev-commands.ps1 dev-test
```

### First run

The first invocation builds the Docker image (a few minutes). Subsequent runs reuse the cached image unless you pass `-NoBuild`:

```powershell
# Force image rebuild
.\run-ci-local.ps1

# Skip rebuild (faster after first run)
.\run-ci-local.ps1 -NoBuild
```

## Recommended Commands

Use the helper script:

```powershell
.\dev-commands.ps1
```

Typical workflow:

- `.\dev-commands.ps1 dev-test` (standard suite)
- `.\dev-commands.ps1 dev-lint`
- `.\dev-commands.ps1 dev-format`
- `.\dev-commands.ps1 dev-make-docs-build`

When needed (credentials/SolidWorks environment available):

- `.\dev-commands.ps1 dev-test-full`

## Testing Expectations

- Add or update tests for behavior changes.
- Keep new behavior covered in the appropriate test module under `tests/`.
- Prefer deterministic tests for CI; keep live/smoke behavior clearly marked.

## Documentation Expectations

- Update docs for user-visible behavior changes.
- Keep architecture docs implementation-accurate.
- Put roadmap/aspirational content in `docs/planning/`, not runtime architecture pages.

Current docs structure:

- `docs/user-guide/` for MCP runtime docs
- `docs/agents/` for agent/skills orchestration and prompt workflows
- `docs/planning/` for future work and roadmap

## Pull Request Guidelines

- Run `.\run-ci-local.ps1` and confirm it passes before opening a PR (see above).
- Use concise commit messages that describe intent.
- Keep unrelated generated/local artifacts out of commits.
- Include validation notes (tests/docs build) in the PR description.
- Link related issues when applicable.

## Bug Reports

Open issues at:

- <https://github.com/andrewbartels1/SolidworksMCP-python/issues>

Helpful bug reports include:

- environment details (OS, Python, SolidWorks version)
- reproduction steps
- expected vs actual behavior
- logs/error output

## License

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE).
