# Tutorial Tracks

Build SolidWorks parts from scratch using the MCP server and Python scripting.

## Track A: Script-Based Part Generation

Best for automated, reproducible builds with direct Python scripting.

**Example:** Build the sample U-bracket from measured sketch coordinates:

```powershell
.\.venv\Scripts\python.exe docs/getting-started/tutorial-parts/build_u_bracket_artifact.py
```

This generates `tutorial-parts/u_bracket_from_prompt.SLDPRT` and an isometric PNG alongside the SolidWorks answer-key render for visual comparison.

**Advantages:**
- Fast, deterministic output
- Repeatable across runs
- Full control over feature sequence
- Easy to version-control and share

**Best for:** CI/CD pipelines, automated testing, generating baseline artifacts

---

## Track B: SolidWorks-as-Code (SoC) Export

Best for capturing a live MCP session as a replayable Python script.

After building a part interactively through MCP tool calls, export the session log as a clean script:

```python
from solidworks_mcp.agents.soc_exporter import export_session

export_session(session_id="...", output_path="my_part.py")
```

The exported script mirrors the structure of `build_u_bracket_artifact.py` — adapter calls, sketch sequences, extrusion parameters — ready to replay or version-control.

**Best for:** Capturing design intent, sharing reproducible builds, checkpoint rewind

---

## Choosing Your Track

| Goal | Track | Reason |
|------|-------|--------|
| Build a known part | A (Script) | Fast, repeatable, CI-ready |
| Capture a live session | B (SoC Export) | Turn interactive work into a script |
| Bulk generation | A (Script) | Automation, minimal overhead |

---

## Available Tutorials

### Reference Artifacts

- **[U-Bracket Build Script](tutorial-parts/build_u_bracket_artifact.py)** — Builds the SolidWorks 2026 sample bracket from measured sketch coordinates; produces `.sldprt` and isometric PNG

### Guided Prompt Packs

- **[U-Joint Rebuild Prompts](tutorial-parts/u_joint_rebuild_prompt.md)** — Pre-written prompts for rebuilding the U-joint if you already have reference samples

---

## Getting Started

Run the reference artifact to verify your MCP setup is working:

```powershell
.\.venv\Scripts\python.exe docs/getting-started/tutorial-parts/build_u_bracket_artifact.py
```

A successful run produces `tutorial-parts/u_bracket_from_prompt.SLDPRT` and two PNG images.
