# Text-to-CAD and CADAM Integration Report

**Last updated:** 2026-07-26  
**Scope:** Evaluate whether this SolidWorks MCP server should reuse existing text-to-CAD technology instead of inventing a new SolidWorks UI and workflow layer from scratch.

---

## Executive Summary

The repo should not replace its SolidWorks execution layer with a new browser UI. The best path is to keep SolidWorks MCP as the system of record for modeling, feature creation, assembly, export, and verification, while borrowing the strongest parts of the upstream CAD ecosystems as planning and handoff layers.

The clearest fit is [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad). It already provides a skills-oriented CAD workflow with inspection, validation, viewer handoff, STEP-first generation, and explicit command boundaries. That makes it a good candidate for LLM-facing wrappers, routing rules, and verification steps.

[Adam-CAD/CADAM](https://github.com/Adam-CAD/CADAM) is useful as a reference for prompt-to-CAD UX, browser rendering, and a polished chat-driven front end. It is not a drop-in for any UI that interfaces with SolidWorks. It is centered on OpenSCAD/WASM and browser preview, so it fits best as inspiration for concept generation or alternate mesh-first output, not as the core of this MCP server.

---
yeah
## Addendum (2026-08-06): Live Verification

Re-checked both upstream repos directly against the GitHub API rather than relying on the original evaluation from memory. Two things changed materially since the original write-up:

**`text-to-cad` is now a directly installable Claude Code / Codex skill, not just a pattern reference.**

- 12,961 stars, MIT licensed, actively maintained (`skills/cad/SKILL.md` last updated same day as this check).
- Installs with `claude plugin marketplace add earthtojake/text-to-cad && claude plugin install cad@text-to-cad`, or via `npx skills install earthtojake/text-to-cad`.
- The `cad` skill generates STEP-first parametric geometry from build123d Python source, with a mandatory validation loop (`scripts/inspect`, `scripts/snapshot`) before handoff, and requires handing the resulting `.step`/`.stp` path to a `$cad-viewer` skill when installed.
- Practical consequence for this repo: **no new SolidWorks MCP code is required for the first integration step.** `open_model` ([src/solidworks_mcp/tools/modeling.py](../../src/solidworks_mcp/tools/modeling.py)) already opens "all standard SolidWorks file formats," which includes STEP. The pipeline `text-to-cad cad skill → validated .step file → open_model(file_path=...)` works today with the skill installed and zero SolidWorks-side changes. Everything downstream (feature-tree edits, drawings, exports) stays on the existing 112-tool SolidWorks-native surface.
- This upgrades the original recommendation from "adapter-level reuse of ideas" to "installable dependency with a working handoff path already present in the codebase."

**`CADAM` confirms the original assessment — not a backend candidate.**

- 4,939 stars, GPLv3, full Next.js/React/Supabase/Vite web app (`src/`, `supabase/`, `vercel.json`, WASM OpenSCAD runtime). No standalone Python/CLI module to embed.
- Nothing in the repo layout changes the original conclusion: useful only as UX/interaction reference, not as an execution engine or dependency.

**Revised recommendation:** treat `solidworks-native` (existing tools) and `text-to-cad` (installed skill, STEP handoff via `open_model`) as the two production-ready branches now. Keep `mesh-concept`/CADAM-style generation as a future, lower-priority branch — it requires a licensing decision and has no ready integration point, unlike `text-to-cad`.

---

## Current Repo Reality

This repository already has the key orchestration pieces that a reusable CAD-skills layer would need:

| Area | Local Surface | Why It Matters |
| --- | --- | --- |
| MCP tool exposure | [src/solidworks_mcp/server.py](../../src/solidworks_mcp/server.py) | The server already exports the tool catalog and can host external toolsets. |
| Workflow selection | [src/solidworks_mcp/ui/services/session_service.py](../../src/solidworks_mcp/ui/services/session_service.py) | The dashboard persists `workflow_mode` and resets state across branches. |
| LLM orchestration | [src/solidworks_mcp/ui/services/llm_service.py](../../src/solidworks_mcp/ui/services/llm_service.py) | Clarify, inspect, and go-orchestration already exist, which is the right insertion point for a CAD skill router. |
| UI entry point | [src/solidworks_mcp/ui/prefab_dashboard.py](../../src/solidworks_mcp/ui/prefab_dashboard.py) | The current UI is an orchestration dashboard, not a CAD authoring app. |
| Automation execution | [src/solidworks_mcp/tools/automation.py](../../src/solidworks_mcp/tools/automation.py) | Best place for workflow pipelines, generator helpers, and future skills wrappers. |

The existing design already assumes the model will decide what to do next, then dispatch into a strict tool surface. That matches a skills-based integration model well.

---

## Upstream Evaluation

### 1. `text-to-cad`

What it is:

- A CAD skills library, not just a single app.
- STEP-first for core CAD workflows.
- Includes inspection, snapshot review, validation, viewer handoff, and command-line entry points.
- Exposes clear skill boundaries for CAD, viewer, URDF, SDF, DXF, G-code, and parts lookup.

Why it fits:

- It already teaches an agent how to think about CAD as a workflow.
- It emphasizes inspect-then-plan-then-execute, which is exactly what 3D-capable LLMs need.
- It gives you a usable pattern for viewer handoff and artifact validation without inventing new UX patterns.

What not to reuse blindly:

- Its output and runtime assumptions are not SolidWorks-native.
- It is optimized around its own skill runtime and artifact pipeline, so the best integration is adapter-level reuse, not wholesale adoption.

### 2. `CADAM`

What it is:

- A browser-based text-to-CAD web app.
- Built around OpenSCAD/WASM, Three.js preview, prompt handling, and chat-style generation.
- Good parameter editing and nice preview UX.

Why it is useful:

- Strong reference for how to expose model controls, previews, and prompt-to-parametric updates.
- Useful for concept generation and fast mesh-style workflows.

Why it is not the right core:

- It is not SolidWorks feature-tree modeling.
- Its stack is centered on web delivery, OpenSCAD, and mesh rendering.
- Its license is GPLv3, which makes direct embedding a separate legal decision.

---

## Recommended Integration Strategy

### Keep SolidWorks MCP as the execution engine

SolidWorks should remain the authoritative backend for:

- part and assembly creation
- sketch and feature operations
- drawing generation and analysis
- export to SolidWorks-compatible and downstream formats
- COM-safe real execution through the existing adapter layer

### Add a skills router instead of a new UI

Introduce a thin planning layer that chooses between:

- native SolidWorks tools
- text-to-cad-style planning and validation
- CADAM-style concept generation or mesh-first fallback workflows

This should be exposed as a tool-selection policy, not as a second front end.

### Treat upstream projects as domain-specific agents

The ideal shape is:

1. User intent enters the existing dashboard or MCP request path.
2. The LLM classifies the intent.
3. A routing layer chooses a skill family.
4. The chosen skill produces a constrained plan.
5. SolidWorks MCP executes the plan.
6. Verification and artifact handoff happen before the user sees success.

---

## Suggested Workflow

### A. SolidWorks-native path

Use this when the user wants editable CAD, assemblies, drawings, or feature-tree work.

Flow:

1. Normalize the request.
2. Ask clarifying questions only when required.
3. Classify the part family or workflow type.
4. Generate a checkpoint plan.
5. Execute the plan with the SolidWorks adapter.
6. Verify via model info, feature-tree checks, mass properties, interference checks, and exports.

### B. Text-to-CAD planning path

Use this when the user wants a clean CAD instruction set, a STEP-first artifact, or a structured workflow that the LLM can reason over.

Flow:

1. Turn the request into a concise manufacturing-ready brief.
2. Choose the right skill family.
3. Produce a constrained tool plan.
4. Emit explicit validation steps and required artifacts.
5. Handoff to viewer or import workflow.

### C. Mesh / concept generation path

Use this when the user wants quick concept art, stylized geometry, or browser-friendly generation that does not need a SolidWorks feature tree.

Flow:

1. Route to a mesh-first or OpenSCAD-style generation tool.
2. Render in a preview surface.
3. Export to a downstream format if needed.
4. Keep the output separate from editable SolidWorks canonical models.

---

## LLM Guardrails

This repo should explicitly teach the model how to use the tool surface, because LLMs are weak at 3D reasoning unless the workflow is constrained.

Recommended guardrails:

- Prefer inspect before execute.
- Never let the model invent tools that do not exist.
- Require explicit units, fit targets, and feature ordering when the model is planning geometry.
- Route sheet metal, advanced solids, or unsupported feature families to specialized handling.
- Verify by artifact, not by prose.
- Use a small number of named skill wrappers instead of a large free-form action space.

This repo already has the beginnings of that pattern in the clarification, classification, and orchestration code paths.

---

## What To Build Next

The most useful follow-up is a small, explicit skill-routing layer with three branches:

| Branch | Purpose | Backing Technology |
| --- | --- | --- |
| `solidworks-native` | Editable SolidWorks modeling | Existing adapter + tools |
| `text-to-cad` | Planning, validation, viewer handoff, STEP-first workflows | Reuse the upstream skill model |
| `mesh-concept` | Fast concept generation / preview | CADAM-style prompt-to-mesh path |

That router should live beside the current orchestration code, not inside the COM adapter.

The likely first implementation target is a new planner tool or service in the automation layer that returns:

- selected skill family
- allowed tools
- required validation steps
- expected outputs
- fallback behavior when confidence is low

---

## Risks And Constraints

- `text-to-cad` is a dependency of ideas and workflow patterns, not an immediate SolidWorks integration drop-in.
- `CADAM` is a different product category and license model, so it should be treated as reference architecture unless there is a deliberate licensing decision.
- If this repo adds too many tool names without strict routing, the LLM will get worse, not better.
- The safest integration is to increase structure, not surface area.

---

## Conclusion

Do not reinvent the whole UI or prompt-to-CAD stack. Reuse the upstream strengths where they actually help:

- `text-to-cad` for CAD skill structure, inspection, validation, and handoff
- `CADAM` for user-facing prompt-to-CAD interaction ideas and preview ergonomics
- this repo for the actual SolidWorks execution path

That gives you a more user-friendly MCP server without diluting SolidWorks semantics or forcing the LLM to reason about 3D geometry without guardrails.
