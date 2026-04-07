# Contributing to SolidWorks MCP Server

Thanks for contributing.

This repository is Python-first and centered on SolidWorks MCP tooling plus optional agent/prompt-testing workflows.

## Development Process

1. Fork the repo and create a branch from `main`.
2. Make focused changes with tests/docs updates where relevant.
3. Run lint/tests/docs build locally.
4. Open a pull request with a concise summary.

## Local Setup

```powershell
git clone https://github.com/<your-username>/SolidworksMCP-python.git
cd SolidworksMCP-python

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs]"
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
