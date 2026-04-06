# Agents and Prompt Testing

This guide is written for people who know SolidWorks well but are new to LLM agents and AI-assisted workflows.

## What Are Agents? (Plain-Language Overview)

If you know SolidWorks, think of agents like this:

| SolidWorks concept | Agent equivalent |
|----|-----|
| Design Intent | Your prompt — what you're trying to build |
| Custom toolbars / macros | Agents — specialists trained for specific tasks |
| Feature Manager checklist | Schema — structured output that validates the result |
| Macro recorder | Skill — a reusable SOP the agent follows |
| Feature history | SQLite log — every prompt and result saved locally |

You write a prompt describing what you want (material, printer, geometry constraints). The agent responds with structured, validated output — not just a chat reply — that can feed directly into your SolidWorks MCP workflow.

---

## What Agents Are Available

Three specialist agents live in `.github/agents/`:

### `solidworks-print-architect`

**Use when:** Designing parts for 3D printing — tolerances, snap fits, overhangs, print orientation, build volume checks.

Example output includes:

- Material tradeoffs (PLA vs PETG vs ABS)
- Snap-fit clearance ranges with risk level
- Which face to put on the print bed and why
- Build volume check against your specific printer

### `solidworks-mcp-skill-docs`

**Use when:** Building SolidWorks MCP workflows, creating tutorials, planning tool sequences from sketch to feature.

Example output includes:

- Step-by-step MCP tool call sequence
- Decision table for tool selection
- Troubleshooting fallbacks
- Demo walkthrough using sample parts from your SolidWorks install

### `solidworks-research-validator`

**Use when:** Fact-checking material specs, looking up printer build volumes, comparing sourcing options before committing to geometry changes.

Example output includes:

- Short answer first
- Evidence table with source and confidence
- Recommended decision with risk level
- Open questions to resolve before CAD work

---

## How to Call the Agents

### Claude Code (This Tool)

The agents in `.github/agents/` are automatically available in Claude Code when you open this repo. Just describe what you need — Claude routes to the right specialist automatically.

### VS Code Copilot Chat

1. Open Copilot Chat (`Ctrl+Alt+I`).
2. Click the agent picker and select one of the three agents.
3. Submit your prompt.

### Command-Line Smoke Test (`smoke_test.py`)

For repeatable, logged tests — results are saved to `.solidworks_mcp/agent_memory.sqlite3`.

---

## First-Time Setup

### Step 1 — Install the Python environment

If you haven't already:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,test]"
```

### Step 2 — Authenticate with GitHub

The smoke test uses GitHub Models, which is free with your GitHub Copilot subscription. You authenticate using the GitHub CLI (`gh`).

Install `gh` if you don't have it:

```powershell
winget install --id GitHub.cli -e --accept-package-agreements --accept-source-agreements
```

Log in (opens browser):

```powershell
gh auth login
```

That's it. The smoke test automatically picks up your `gh` credentials — no environment variables needed.

!!! warning "If `gh auth login` says `GH_TOKEN` is being used"
  GitHub CLI gives environment variables precedence over stored credentials. If you see:

  `The value of the GH_TOKEN environment variable is being used for authentication.`

  clear the token from the current shell and your saved user environment first, then log in again:

  ```powershell
  Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
  Remove-Item Env:GITHUB_API_KEY -ErrorAction SilentlyContinue
  [System.Environment]::SetEnvironmentVariable("GH_TOKEN", $null, "User")
  [System.Environment]::SetEnvironmentVariable("GITHUB_API_KEY", $null, "User")
  gh auth logout -h github.com
  gh auth login
  gh auth status
  ```

  After that, open a new terminal before rerunning smoke tests.

!!! tip "Already logged in?"
    Run `gh auth status` to confirm. If it shows your account, you're ready to run tests immediately.

### Step 3 — Run your first test

```powershell
.\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test `
  --agent-file solidworks-print-architect.agent.md `
  --github-models `
  --schema manufacturability `
  --prompt "Design a PLA snap-fit battery cover for a 220x220x250 bed"
```

You should see structured JSON output like this:

```json
{
  "summary": "Snap-fit battery cover for PLA ...",
  "assumptions": [...],
  "recommendations": [
    { "title": "Use conservative snap thickness", "risk": "medium", ... },
    ...
  ],
  "orientation_guidance": "Print face-down with exterior cover surface on bed ...",
  "tolerance_clearance_notes": ["0.3-0.5 mm clearance for snap fits ..."],
  "build_volume_check": "Part fits within 220x220x250 mm envelope ..."
}
```

---

## Provider Setup Options

=== "GitHub Models (Recommended — free with Copilot)"

    Uses your existing GitHub Copilot subscription. No separate API key or billing.

    **Automatic (via `gh` CLI — recommended):**

    The smoke test falls back to `gh auth token` automatically if no environment variable is set. Just run `gh auth login` once.

    If `gh auth login` refuses to store credentials because `GH_TOKEN` is already set, clear both `GH_TOKEN` and `GITHUB_API_KEY`, then authenticate again:

    ```powershell
    Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:GITHUB_API_KEY -ErrorAction SilentlyContinue
    [System.Environment]::SetEnvironmentVariable("GH_TOKEN", $null, "User")
    [System.Environment]::SetEnvironmentVariable("GITHUB_API_KEY", $null, "User")
    gh auth logout -h github.com
    gh auth login
    gh auth status
    ```

    **Manual (if you prefer explicit env vars):**

    ```powershell
    # Save permanently
    $token = gh auth token
    [System.Environment]::SetEnvironmentVariable("GH_TOKEN", $token, "User")

    # Load into current session
    $env:GH_TOKEN = [System.Environment]::GetEnvironmentVariable("GH_TOKEN", "User")
    ```

    Run smoke test:

    ```powershell
    .\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test `
      --agent-file solidworks-print-architect.agent.md `
      --github-models `
      --schema manufacturability `
      --prompt "Design a PLA snap-fit battery cover for 220x220x250 bed and include orientation guidance"
    ```

=== "GitHub Copilot Subscription (VS Code + Copilot CLI)"

    Use this for interactive day-to-day usage in VS Code chat.

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

=== "OpenAI API (BYOK)"

    1. Create an OpenAI API key.
    2. Export key:

    ```powershell
    $env:OPENAI_API_KEY = "<your_openai_api_key>"
    ```

    3. Run smoke test with OpenAI provider model:

    ```powershell
    .\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test `
      --agent-file solidworks-print-architect.agent.md `
      --model openai:gpt-4.1 `
      --schema manufacturability `
      --prompt "Design a PLA snap-fit battery cover for 220x220x250 bed and include orientation guidance"
    ```

=== "Anthropic API (BYOK)"

    Requires an Anthropic account with active billing credits (separate from Claude Code subscription).
    Get your key at: https://console.anthropic.com/settings/keys

    ```powershell
    [System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-...", "User")
    $env:ANTHROPIC_API_KEY = [System.Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY", "User")
    ```

    Run smoke test:

    ```powershell
    .\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test `
      --agent-file solidworks-print-architect.agent.md `
      --anthropic `
      --schema manufacturability `
      --prompt "Design a PLA snap-fit battery cover for 220x220x250 bed and include orientation guidance"
    ```

Credential rules summary:

- `--github-models` auto-uses `gh auth token` if `GH_TOKEN`/`GITHUB_API_KEY` are not set.
- `--model openai:*` requires `OPENAI_API_KEY`.
- `--anthropic` requires `ANTHROPIC_API_KEY` with active billing.
- Copilot subscription entitlements are not reused as OpenAI/Anthropic API keys.

---

## What Each Schema Validates

Every smoke test produces one of two structured output types:

### `--schema manufacturability`

Used with `solidworks-print-architect` and `solidworks-research-validator`.

| Field | What it tells you |
|---|---|
| `summary` | One-paragraph design verdict |
| `assumptions` | What the agent assumed about your printer, material, geometry |
| `recommendations` | Specific changes with title, rationale, and risk level |
| `orientation_guidance` | Which face goes on the bed and why |
| `tolerance_clearance_notes` | Exact mm ranges to use in your SolidWorks sketch |
| `build_volume_check` | PASS/FAIL against your printer envelope |

### `--schema docs`

Used with `solidworks-mcp-skill-docs` and any agent when planning a tutorial.

| Field | What it tells you |
|---|---|
| `audience` | Who the doc is for |
| `objective` | What the reader will be able to do |
| `sections` | Doc outline |
| `decisions` | Tool selection decisions with fallback strategies |
| `demo_steps` | Copy-paste walkthrough sequence |

---

## Verified Smoke Test Results

All six combinations below pass with `--github-models` using a GitHub Copilot subscription:

| Agent | Schema | Sample prompt |
|---|---|---|
| `solidworks-print-architect` | `manufacturability` | PLA snap-fit battery cover, 220×220×250 bed |
| `solidworks-print-architect` | `manufacturability` | ABS enclosure for RPi4, Bambu X1C, 0.4 mm nozzle |
| `solidworks-print-architect` | `docs` | Tutorial: 3D printed hinge with correct tolerances |
| `solidworks-mcp-skill-docs` | `docs` | Tutorial: bracket creation with MCP tools |
| `solidworks-mcp-skill-docs` | `manufacturability` | Bracket sketch-to-extrusion printability review |
| `solidworks-research-validator` | `manufacturability` | PETG outdoor enclosure material validation |
| `solidworks-research-validator` | `docs` | FDM printer build volume comparison page |

---

## Example Prompts for SolidWorks Users

### You know the part, you need print guidance

```
solidworks-print-architect, manufacturability:
"Design a PETG clip-on cable cover for outdoor use.
 Printer: Bambu X1C (256x256x256 bed), 0.4mm nozzle, 0.2mm layer height.
 Give tolerance/clearance ranges and orientation guidance."
```

### You know the assembly, you need a workflow

```
solidworks-mcp-skill-docs, docs:
"Plan a step-by-step MCP workflow for creating the U-Joint assembly
 from the SolidWorks 2026 sample learn folder.
 Include tool names, fallback strategies, and troubleshooting."
```

### You need to verify a material spec before starting

```
solidworks-research-validator, manufacturability:
"Verify ABS vs PETG heat resistance for an enclosure mounted near a
 car engine bay. Ambient max ~80°C. What wall thickness is safe?"
```

### You want to check if a part fits the printer

```
solidworks-print-architect, manufacturability:
"I have an L-bracket: 180mm long, 80mm tall, 3mm thick.
 Does it fit a Prusa MK4 (250x210x220 bed)?
 Which face should be on the bed?"
```

---

## Prompts, Skills, and Agents (Mental Model for SolidWorks Engineers)

| Concept | SolidWorks equivalent | What it does in this project |
|---|---|---|
| Prompt | Your design brief / RFQ | Tells the agent exactly what to evaluate |
| Agent | A specialist engineer | Holds domain expertise and behavior rules |
| Skill | A validated SOP or checklist | Reusable instructions for focused tasks |
| Schema | Acceptance criteria / GD&T callout | Forces structured, machine-checkable output |
| Harness | Test fixture | Runs prompts, validates output, logs results |

### Agents (`.github/agents/*.agent.md`)

Agents define the persona, scope, constraints, and output style for a specialist. They are plain Markdown files — you can read and edit them directly.

### Skills (`.github/skills/**/SKILL.md`)

Skills are invoked for a specific focused task. Example: `printer-profile-tolerancing` takes a printer model + material and outputs exact tolerance ranges for every joint type.

### Schemas (`src/solidworks_mcp/agents/schemas.py`)

Schemas turn free-form AI responses into validated data structures. If the model returns something that doesn't match the schema, the harness catches it and retries automatically.

---

## Harness and Retry Behavior

```powershell
# Run with 2 automatic retries on recoverable failures
.\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test `
  --agent-file solidworks-print-architect.agent.md `
  --github-models `
  --schema manufacturability `
  --max-retries-on-recoverable 2 `
  --prompt "Design a PLA snap-fit battery cover for 220x220x250 bed"
```

```powershell
# Run a docs-focused validation
.\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test `
  --agent-file solidworks-mcp-skill-docs.agent.md `
  --github-models `
  --schema docs `
  --prompt "Plan a tutorial page that demonstrates routing from sketch to extrusion with fallback troubleshooting"
```

---

## Local SQLite Memory for Error-Driven Recovery

The harness writes to:

- `.solidworks_mcp/agent_memory.sqlite3`

Tables (managed through SQLModel):

- `agent_runs`: each prompt run and status
- `tool_events`: optional lifecycle events for tool usage
- `error_catalog`: normalized root cause + remediation entries

Use this data to prevent repeated failures from a broken state, and to drive rollback-first troubleshooting prompts.

Query recent failures in PowerShell:

```powershell
# Requires sqlite3 on PATH, or use DB Browser for SQLite (free GUI)
sqlite3 .solidworks_mcp\agent_memory.sqlite3 "SELECT agent_name, status, prompt FROM agent_runs ORDER BY created_at DESC LIMIT 10;"
```

---

## Suggested Workflow

1. **Before geometry work** — run `solidworks-research-validator` to confirm material properties and printer specs.
2. **During design** — use `solidworks-print-architect` to check tolerances, orientation, and build volume fit.
3. **When building workflows** — use `solidworks-mcp-skill-docs` to plan the MCP tool sequence and generate tutorial docs.
4. **When something fails** — check `.solidworks_mcp/agent_memory.sqlite3` error catalog before retrying.

---

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
