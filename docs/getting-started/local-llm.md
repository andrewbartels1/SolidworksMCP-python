# Local LLM with Ollama (Gemma 4)

The SolidWorks MCP UI can route all LLM calls to a local Ollama instance instead of GitHub Models or OpenAI. This works offline, keeps design data private, and uses Ollama's OpenAI-compatible endpoint at `http://127.0.0.1:11434/v1`.

The official Ollama Gemma 4 library page is here: <https://ollama.com/library/gemma4>

## What the Ollama Gemma 4 docs say

The current Ollama Gemma 4 tags relevant to this project are:

| Tier | Ollama tag | Context | Best for |
| ---- | ---------- | ------- | -------- |
| Small | `gemma4:e2b` | 128K | CPU-friendly edge and smoke tests |
| Balanced | `gemma4:e4b` | 128K | Recommended default for local planning |
| Large | `gemma4:26b` | 256K | Workstation-class local evaluation |
| XL | `gemma4:31b` | 256K | Highest-cost local evaluation |

Notes from the Ollama page:

- `gemma4:e2b` and `gemma4:e4b` are the edge variants.
- `gemma4:26b` and `gemma4:31b` are the workstation variants.
- Gemma 4 exposes native `system` role support and a much larger context window than earlier local defaults.
- The repo currently auto-detects `small`, `balanced`, and `large`; `31b` remains a manual override because it is above the current large-tier threshold.

!!! tip "Auto-selection"
    The `/api/ui/local-model/probe` endpoint detects GPU VRAM and system RAM, then recommends one of the built-in Gemma 4 tiers.

## Setup

### 1. Install and start Ollama

```powershell
# Download from https://ollama.com and install, then verify:
ollama serve
```

### 2. Pull the recommended model

```powershell
# Let the backend pick for you based on your hardware:
# GET http://127.0.0.1:8766/api/ui/local-model/probe
# Then use the returned `pull_command`, for example:

ollama pull gemma4:e4b
```

Or pull a specific tier directly:

```powershell
ollama pull gemma4:e2b   # small
ollama pull gemma4:e4b   # balanced (recommended)
ollama pull gemma4:26b   # large
ollama pull gemma4:31b   # manual high-end override
```

### 2a. Using the UI controls instead of raw commands

In `Design Spec and Model Settings`:

1. Click `Provider: Local`.
2. Click `Auto-Detect Local Model`.
3. Review the recommended tier, endpoint, and pull command shown under the model controls.
4. If the model is not downloaded yet, click `Pull Recommended Model`.
5. Run `Auto-Detect Local Model` again to refresh availability, then retry Clarify or Inspect.

This is the intended recovery path for errors like:

```text
model 'llama3.1' not found
```

### 3. Configure the UI to use local inference

Set the model in your environment before starting the UI server:

```powershell
# Option A — environment variable for the current shell
$env:SOLIDWORKS_UI_MODEL = "local:gemma4:e4b"
.\run-ui.ps1

# Option B — one-line launch
$env:SOLIDWORKS_UI_MODEL = "local:gemma4:e4b"; .\run-ui.ps1
```

Available `SOLIDWORKS_UI_MODEL` values for local inference:

| Value | Tier |
| ----- | ---- |
| `local:gemma4:e2b` | small |
| `local:gemma4:e4b` | balanced |
| `local:gemma4:26b` | large |
| `local:gemma4:31b` | manual override |

### 4. Optional custom Ollama endpoint

If you run Ollama on a different host or port:

```powershell
$env:SOLIDWORKS_UI_OLLAMA_ENDPOINT = "http://my-gpu-server:11434"
$env:SOLIDWORKS_UI_LOCAL_ENDPOINT = "http://my-gpu-server:11434/v1"
```

## API Endpoints

### `GET /api/ui/local-model/probe`

Returns hardware info and the recommended model tier.

```json
{
  "available": true,
  "endpoint": "http://127.0.0.1:11434",
  "tier": "balanced",
  "ollama_model": "gemma4:e4b",
  "service_model": "local:gemma4:e4b",
  "label": "Gemma 4 E4B (balanced — 8 GB VRAM)",
  "vram_gb": 10.8,
  "ram_gb": 32.0,
  "pulled_models": ["gemma4:e4b"],
  "tier_already_pulled": true,
  "pull_command": "ollama pull gemma4:e4b",
  "status_message": "Ready: Gemma 4 E4B (balanced — 8 GB VRAM) is loaded in Ollama."
}
```

### `POST /api/ui/local-model/pull`

Pull a model into Ollama. Body: `{"model": "gemma4:e4b"}`.

```json
{ "queued": true, "model": "gemma4:e4b" }
```

## Troubleshooting

**`Ollama is not running`**
: Start Ollama with `ollama serve` or ensure the desktop app is running.

**`tier_already_pulled: false`**
: Run the `pull_command` shown in the probe response to download the recommended tag.

**Slow generation**
: Use the `small` tier `gemma4:e2b` for CPU-bound or constrained-memory systems.

**VRAM detected as 0**
: CUDA drivers may be unavailable or the machine may be using an iGPU. The `small` tier will still run, but more slowly.
