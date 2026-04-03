# SolidWorks MCP Server (Python)

This file is the quick orientation guide for contributors and coding agents.

## Platform and Runtime

- Primary runtime is Python 3.11+.
- Real COM automation requires Windows + SolidWorks installed.
- Cross-platform development is possible in mock/test mode.

## Build and Development Commands

Use either micromamba environment commands or local virtualenv commands.

### Preferred PowerShell workflow

```powershell
# Show command help
.\dev-commands.ps1

# Full install in micromamba env
.\dev-commands.ps1 dev-install

# Fast test pass (no SolidWorks-required tests)
.\dev-commands.ps1 dev-test

# Full test run including real SolidWorks integration
.\dev-commands.ps1 dev-test-full

# Lint and format
.\dev-commands.ps1 dev-lint
.\dev-commands.ps1 dev-format

# Docs build/serve
.\dev-commands.ps1 dev-make-docs-build
.\dev-commands.ps1 dev-docs
```

### Virtualenv direct workflow

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs]"

# Run server
.\.venv\Scripts\python.exe -m solidworks_mcp.server

# Lint/tests/docs
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m pytest tests -m "not solidworks_only"
.\.venv\Scripts\python.exe -m mkdocs build --clean
```

## Architecture

- Server entrypoint: `src/solidworks_mcp/server.py`
- CLI entrypoint: `src/solidworks_mcp/server_cli_fixed.py`
- Adapters: `src/solidworks_mcp/adapters/`
  - `pywin32_adapter.py`: real SolidWorks COM adapter (Windows)
  - `mock_adapter.py`: mock adapter for tests and CI-like runs
  - `factory.py`: adapter selection/routing logic
- Tools: `src/solidworks_mcp/tools/` (modeling, sketching, drawing, export, analysis, automation, templates, VBA, docs discovery)
- Agent harness: `src/solidworks_mcp/agents/` (prompt schemas, smoke test CLI, run/error persistence)

## Key Patterns

### COM and Adapter Safety

- Prefer adapter abstraction, not direct COM calls from tool modules.
- Keep Windows/COM behavior behind adapter boundaries.
- Use mock adapter for tests unless a test explicitly requires real SolidWorks.

### Logging and Output

- Use project logging utilities (`loguru`/configured helpers).
- Avoid ad-hoc print statements in runtime server paths.

### Validation and Tool Contracts

- Keep tool input schemas strict and explicit.
- Maintain stable response payload shapes (`status`, `message`, `execution_time`, plus data payload).

## Testing Guidance

- Default local path: run non-`solidworks_only` tests first.
- Real integration path: run `dev-test-full` on Windows with SolidWorks available.
- Harness and generated report artifacts may write under `tests/.generated/` and `.solidworks_mcp/`.

## Documentation Guidance

- Build docs before commit when touching docs pages:
  - `.\dev-commands.ps1 dev-make-docs-build`
- For local preview:
  - `.\dev-commands.ps1 dev-docs`

## Agent and Model Notes

- VS Code Copilot subscription is suitable for chat-based workflows.
- Local Python smoke tests require explicit provider credentials:
  - GitHub Models: `GH_TOKEN` or `GITHUB_API_KEY`
  - OpenAI: `OPENAI_API_KEY`
  - Anthropic: `ANTHROPIC_API_KEY`
