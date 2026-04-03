# Agents and Prompt Testing

This guide is for users who already know SolidWorks workflows but are newer to LLM agents.

## What You Now Have

Workspace agents in `.github/agents/`:

1. `solidworks-print-architect.agent.md`

- Design-for-print guidance (tolerances, clearances, orientation, material tradeoffs)
- Build-volume checks and mitigation strategies

1. `solidworks-mcp-skill-docs.agent.md`

- Skill/service design for better MCP tool routing
- Docs and demo workflow authoring

1. `solidworks-research-validator.agent.md`

- Fast read-only fact validation (materials, printer specs, sourcing)

## How to Call the Agents in VS Code

1. Open Copilot Chat.
2. Choose the target custom agent in the chat agent picker.
3. Submit your prompt.

Advanced delegation:

- Use your main agent and ask it to hand off to one of the specialized agents by name when appropriate.

## Installation and Model Setup

Use this section when setting up agent testing for the first time.

### Pick Your Runtime Path

1. VS Code Copilot Chat path

- Uses your Copilot subscription directly in VS Code.
- Best for interactive day-to-day usage.

1. Local `pydantic-ai` smoke test path

- Runs as a normal Python process.
- Requires credentials for the model provider you choose.

### Provider Setup (Tabbed)

=== "GitHub Copilot Subscription (VS Code + Copilot CLI)"

    Use this if you want subscription-backed usage in VS Code and terminal Copilot CLI workflows.

    Install GitHub CLI on Windows:

    ```powershell
    winget install --id GitHub.cli -e --accept-package-agreements --accept-source-agreements
    ```

    Authenticate:

    ```powershell
    gh auth login
    ```

    Ensure `gh` is on PATH (User PATH, Windows):

    ```powershell
    $ghDir = "C:\Program Files\GitHub CLI"
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$ghDir*") {
      [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(';') + ';' + $ghDir).Trim(';'), "User")
    }
    ```

    Install/verify Copilot CLI:

    ```powershell
    gh copilot -- --help
    copilot --help
    ```

    If `copilot` is still not found, add its install directory to PATH:

    ```powershell
    $copilotDir = "$env:APPDATA\Code\User\globalStorage\github.copilot-chat\copilotCli"
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$copilotDir*") {
      [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(';') + ';' + $copilotDir).Trim(';'), "User")
    }
    ```

    Model selection notes:

    - Copilot CLI uses the default configured model when `--model` is omitted.
    - This is the practical equivalent of "auto" behavior in CLI usage.
    - Pin a model only when needed, for example: `copilot --model gpt-5.3-codex`.

=== "GitHub Models (Recommended for local smoke tests)"

    Use this if you want local `smoke_test.py` runs without OpenAI/Anthropic direct billing.

    1. Create a GitHub PAT with `models:read` scope.
    2. Export token to environment:

    ```powershell
    $env:GH_TOKEN = "<your_github_pat_with_models_read>"
    # or
    $env:GITHUB_API_KEY = "<your_github_pat_with_models_read>"
    ```

    3. Run smoke test:

    ```powershell
    .\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test --agent-file solidworks-print-architect.agent.md --github-models --github-model openai/gpt-4.1 --schema manufacturability --prompt "Design a PLA snap-fit battery cover for 220x220x250 bed and include orientation guidance"
    ```

=== "OpenAI API (BYOK)"

    1. Create an OpenAI API key.
    2. Export key:

    ```powershell
    $env:OPENAI_API_KEY = "<your_openai_api_key>"
    ```

    3. Run smoke test with OpenAI provider model:

    ```powershell
    .\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test --agent-file solidworks-print-architect.agent.md --model openai:gpt-4.1 --schema manufacturability --prompt "Design a PLA snap-fit battery cover for 220x220x250 bed and include orientation guidance"
    ```

=== "Anthropic API (BYOK)"

    1. Create an Anthropic API key.
    2. Export key:

    ```powershell
    $env:ANTHROPIC_API_KEY = "<your_anthropic_api_key>"
    ```

    3. Run smoke test with Anthropic provider model:

    ```powershell
    .\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test --agent-file solidworks-print-architect.agent.md --model anthropic:claude-3-5-sonnet-latest --schema manufacturability --prompt "Design a PLA snap-fit battery cover for 220x220x250 bed and include orientation guidance"
    ```

Credential rules summary:

- `--github-models` requires `GH_TOKEN` or `GITHUB_API_KEY`.
- `--model openai:*` requires `OPENAI_API_KEY`.
- `--model anthropic:*` requires `ANTHROPIC_API_KEY`.
- Copilot subscription entitlements are not reused as OpenAI/Anthropic API keys for local Python runs.

## Prompts, Skills, and Agents (Engineer-Friendly)

If you know SolidWorks and engineering workflows but are new to LLM systems, use this mental model:

- Prompt: your job ticket.
- Agent: your specialist engineer profile.
- Skill: your reusable SOP/checklist.
- Schema: your acceptance criteria.

How each piece maps in this repository:

1. Prompts

- Prompts are the direct requests you send (for example manufacturability checks, orientation guidance, or tolerance recommendations).
- Good prompts include geometry intent, constraints, material, printer limits, and required output format.

1. Agents (`.github/agents/*.agent.md`)

- Agents define behavior and boundaries for a domain specialist persona.
- Example: `solidworks-print-architect.agent.md` focuses on printability decisions and risk-aware recommendations.

1. Skills (`.github/skills/**/SKILL.md`)

- Skills are reusable instructions invoked for focused tasks (for example tolerancing guidance).
- Think of a skill as a validated playbook that reduces prompt drift and improves consistency.

1. Schemas (`src/solidworks_mcp/agents/schemas.py`)

- Schemas force structured outputs so results can be validated and stored.
- This is how the harness turns natural-language responses into reliable, machine-checkable artifacts.

1. Harness (`src/solidworks_mcp/agents/smoke_test.py` + `harness.py`)

- The harness runs prompts against an agent and validates output against a selected schema.
- Recoverable failures are captured with remediation steps so you can retry with a narrower scope.

Recommended learning sequence:

1. Start in VS Code Copilot Chat with one specialized agent.
2. Use short, constraint-rich prompts (material, bed size, tolerance target, orientation requirement).
3. Move to `smoke_test.py` when you need repeatable validation and logged outputs.
4. Review `.solidworks_mcp/agent_memory.sqlite3` when results fail or need iteration history.

## Example Prompts

### SolidWorks Print Architect

- "Design a clip-on cover in PETG for outdoor use and give tolerance/clearance ranges plus orientation guidance."
- "I need this entire assembly to fit a 256x256x256 mm print bed. Suggest split points and joint strategy."
- "Given a 0.4 mm nozzle and 0.2 mm layer height, propose conservative snap-fit dimensions and risks."

### SolidWorks MCP Skill and Docs Engineer

- "Create a tool-routing skill for sketch-to-feature workflows with fallback when sketches are invalid."
- "Generate a docs demo for a bracket workflow using the SOLIDWORKS sample learn folder."
- "Draft a decision table for when to use drawing-analysis tools vs modeling tools."

### SolidWorks Research Validator

- "Compare McMaster-Carr shoulder screw options vs commodity listings for a printable hinge pin design."
- "Verify real-world build volume for Bambu X1C and whether this part at 280 mm length fits."
- "Fact-check PETG and ASA thermal behavior assumptions for this enclosure concept."

## PydanticAI Prompt Validation Harness

A starter harness is available in `src/solidworks_mcp/agents/`.

Key modules:

- `harness.py`: runs a prompt against a selected `.agent.md` file, validates typed output, and persists success/recoverable-failure/error states.
- `schemas.py`: reusable validation schemas for manufacturability and docs planning outputs.
- `history_db.py`: SQLModel-based local SQLite logging of runs, tool events, and normalized errors.
- `smoke_test.py`: CLI runner for quick prompt validation.

For provider-specific setup and baseline smoke-test commands, use **Installation and Model Setup** above.

Enable extra retry attempts on model-directed recoverable failures:

```powershell
.\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test --agent-file solidworks-print-architect.agent.md --model openai:gpt-4.1 --schema manufacturability --max-retries-on-recoverable 2 --prompt "Design a PLA snap-fit battery cover for 220x220x250 bed and include orientation guidance"
```

Run a docs-focused validation:

```powershell
.\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test  --agent-file solidworks-mcp-skill-docs.agent.md  --model openai:gpt-4.1  --schema docs  --prompt "Plan a tutorial page that demonstrates routing from sketch to extrusion with fallback troubleshooting"
```

## Local SQLite Memory for Error-Driven Recovery

The harness writes to:

- `.solidworks_mcp/agent_memory.sqlite3`

Tables (managed through SQLModel):

- `agent_runs`: each prompt run and status
- `tool_events`: optional lifecycle events for tool usage
- `error_catalog`: normalized root cause + remediation entries

Use this data to prevent repeated failures from a broken state, and to drive rollback-first troubleshooting prompts.

## Environment Warning: RequestsDependencyWarning

If you see:

`RequestsDependencyWarning: urllib3 (...) or chardet (...)/charset_normalizer (...) doesn't match a supported version`

the root cause is usually an unsupported `chardet` major version installed in the venv.

This project now pins `chardet<6` in `pyproject.toml`. To fix an existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Then verify:

```powershell
.\.venv\Scripts\python.exe -W default -c "import requests; print(requests.__version__)"
```

## Continuing Customizations

1. Added read-only research validator agent (`solidworks-research-validator.agent.md`).
2. Added printer-profile tolerancing skill (`.github/skills/printer-profile-tolerancing/SKILL.md`).
3. Added reusable docs demo prompt (`.github/prompts/docs-demo-template.prompt.md`).

## Suggested Workflow

1. Start with `solidworks-research-validator` for uncertain material/printer assumptions.
2. Move to `solidworks-print-architect` for geometry/tolerance/orientation decisions.
3. Use `solidworks-mcp-skill-docs` to encode repeatable tool routing and publish docs demos.
4. Run smoke tests and inspect SQLite error catalog before rolling into larger workflows.
