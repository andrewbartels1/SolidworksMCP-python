# Local LLM with Ollama (Gemma 3 / Gemma 4)

The SolidWorks MCP UI can route all LLM calls to a **local Ollama instance** instead of GitHub Models or OpenAI.
This works offline, keeps design data private, and costs nothing after the initial model download.

## Supported Models

| Tier | Ollama tag | VRAM needed | Best for |
|------|-----------|-------------|----------|
| Small | `gemma3:4b` | CPU or ≥ 4 GB | Quick iteration, low-end hardware |
| Balanced | `gemma3:12b` | ≥ 8 GB | Recommended default (RTX 3070 / 4070) |
| Large | `gemma3:27b` | ≥ 18 GB | High-end GPU (RTX 3090 / 4090 / A100) |

!!! tip "Auto-selection"
    The `/api/ui/local-model/probe` endpoint detects your GPU VRAM and RAM automatically
    and picks the best tier.

## Setup

### 1. Install Ollama

```powershell
# Download from https://ollama.com and install, then verify:
ollama serve          # starts the API server (http://127.0.0.1:11434)
```

### 2. Pull the recommended model

```powershell
# Let the server pick for you based on your hardware:
# GET http://127.0.0.1:8766/api/ui/local-model/probe
# Then use the returned `pull_command` value, e.g.:

ollama pull gemma3:12b
```

Or pull a specific tier directly:

```powershell
ollama pull gemma3:4b    # small — works on CPU
ollama pull gemma3:12b   # balanced (recommended)
ollama pull gemma3:27b   # large (needs ≥ 18 GB VRAM)
```

### 3. Configure the UI to use local inference

Set the model in your environment before starting the UI server:

```powershell
# Option A — environment variable (persists for the shell session)
$env:SOLIDWORKS_UI_MODEL = "local:google/gemma-3-12b-it"
.\run-ui.ps1

# Option B — per-run prefix
$env:SOLIDWORKS_UI_MODEL="local:google/gemma-3-12b-it"; .\run-ui.ps1
```

Available `SOLIDWORKS_UI_MODEL` values for local inference:

| Value | Tier |
|-------|------|
| `local:google/gemma-3-4b-it` | small |
| `local:google/gemma-3-12b-it` | balanced |
| `local:google/gemma-3-27b-it` | large |

### 4. (Optional) Custom Ollama endpoint

If you run Ollama on a different host or port:

```powershell
$env:SOLIDWORKS_UI_OLLAMA_ENDPOINT = "http://my-gpu-server:11434"
$env:SOLIDWORKS_UI_LOCAL_ENDPOINT  = "http://my-gpu-server:11434/v1"
```

## API Endpoints

### `GET /api/ui/local-model/probe`

Returns hardware info and the recommended model tier.

```json
{
  "available": true,
  "endpoint": "http://127.0.0.1:11434",
  "tier": "balanced",
  "ollama_model": "gemma3:12b",
  "service_model": "local:google/gemma-3-12b-it",
  "label": "Gemma 3 12B (balanced — 8 GB VRAM)",
  "vram_gb": 10.8,
  "ram_gb": 32.0,
  "pulled_models": ["gemma3:12b"],
  "tier_already_pulled": true,
  "pull_command": "ollama pull gemma3:12b",
  "status_message": "Ready: Gemma 3 12B (balanced — 8 GB VRAM) is loaded in Ollama."
}
```

### `POST /api/ui/local-model/pull`

Pull a model into Ollama.  Body: `{"model": "gemma3:12b"}`.

```json
{ "queued": true, "model": "gemma3:12b" }
```

## Troubleshooting

**`Ollama is not running`**
: Start Ollama: `ollama serve` (or ensure the Ollama desktop app is running).

**`tier_already_pulled: false`**
: Run the `pull_command` shown in the probe response to download the model.

**Slow generation**
: Use the `small` tier (`gemma3:4b`) which can run on CPU with quantization.

**VRAM detected as 0**
: cuda drivers not found or GPU is iGPU — the `small` tier will still work but at CPU speed.
