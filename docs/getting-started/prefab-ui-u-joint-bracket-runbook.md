# Prefab UI Runbook: U-Joint Bracket From Scratch (Local Gemma)

This runbook is a tested, operator-first flow for building a printable bracket using the U-Joint sample set as reference geometry and feature-tree evidence.

It is aligned to:

- `docs/getting-started/prefab-ui-dashboard.md`
- `docs/planning/REFACTOR_UI_ASSESSMENT.md`

It also includes explicit handling for currently mocked or partial features, so the workflow remains reliable end-to-end.

## 1. Goal and constraints used in this run

- Material: PETG
- Layer height: 0.2 mm
- Nozzle: 0.6 mm
- Mating tolerance / clearance budget: 1.0 mm
- Design intent: printable cable-routing style bracket with robust walls and M4-ready mounting references

## 2. Reference model set (U-Joint sample)

Path used:

`C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint`

Discovered sample files:

- `bracket.sldprt`
- `UJoint.SLDASM`
- `crank sub.SLDASM`
- `crank-arm.sldprt`
- `crank-knob.sldprt`
- `crank-shaft.sldprt`
- `pin.sldprt`
- `spider.sldprt`
- `Yoke_female.sldprt`
- `Yoke_male.sldprt`

Feature-tree snapshot read for `bracket.sldprt` in this run:

- `Sketch1`
- `Base-Extrude-Thin`
- `Sketch2`

Use these names directly in feature targets when grounding checkpoints.

## 3. Required services

Terminal A (backend):

```powershell
.\.venv\Scripts\python.exe -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port 8766
```

Terminal B (Prefab UI):

```powershell
.\.venv\Scripts\prefab.exe serve src/solidworks_mcp/ui/prefab_dashboard.py
```

Optional but recommended for retrieval index support:

```powershell
.\.venv\Scripts\python.exe -m pip install faiss-cpu
```

## 4. Local Gemma inference setup

This runbook uses local inference for Clarify and Inspect.

1. Confirm Ollama endpoint:
   - `http://127.0.0.1:11434/v1`
2. In UI, run **Auto-Detect Local Model**.
3. Set / verify:
   - Provider: `local`
   - Profile: `small` (or `balanced`)
   - Model name: `local:gemma4:e2b` (or your detected Gemma tier)
4. Click **Save Preferences**.

If local model is missing, click **Pull Recommended Model**, then re-run **Auto-Detect Local Model**.

## 5. Design Spec prompt with exact dimensions (paste exactly)

Use this in the Design goal textbox:

> Start from a blank part and create a PETG U-bracket using explicit dimensions only (do not infer hidden dimensions from existing features): overall envelope 78 mm (X) x 52 mm (Y) x 36 mm (Z). Use wall thickness 1.8 mm minimum and target 2.4 mm on load paths (multiples of a 0.6 mm nozzle). Sketch1 must define the base profile with an outer rectangle 78 x 52 mm, inner clearance window 60 x 34 mm centered, and 9 mm corner fillets on the outer corners. Create a thin/base extrusion to 36 mm height with 2.4 mm wall thickness. Sketch2 must add mounting refinements: two M4 reference holes on the flange centerline at X offsets +/-24 mm, hole pilot diameter 4.2 mm, and one cable slot 16 x 8 mm centered on the inner face. Enforce 1.0 mm mating clearance budget where interfaces move or mate. Then compare this from-scratch geometry against U-Joint bracket guidance (feature-tree names and proportions) and report any dimensional mismatch before executing irreversible steps.

Use this in Assumptions:

> Material PETG. Layer height 0.2 mm. Nozzle 0.6 mm. Clearance/tolerance budget 1.0 mm for mating interfaces. Prefer ribs/fillets over sharp stress risers. Avoid long unsupported bridges. Keep feature naming stable for downstream checkpoint targeting.

### 5.1 Why this exact prompt structure

- It forces explicit dimensions when starting from zero (no hidden model dependence).
- It still uses U-Joint as guidance for topology and naming checks.
- It gives the planner concrete sketch/extrude inputs so tool-call validation is auditable.

## 6. Clarification answers (recommended)

If Clarify asks follow-ups, answer with this guidance:

- Mounting standard: M4 hardware, hole strategy can be pilot + post-drill or direct clearance depending on printer calibration
- Minimum wall thickness: 1.8 mm preferred baseline (3x nozzle) unless local loads require more
- Interface clearance: 1.0 mm budget for mating regions in this exercise
- Orientation priority: orient to reduce support and keep critical mating faces dimensionally stable
- Success criteria: model opens cleanly, feature tree remains editable, preview exports all views, checkpoint evidence is traceable

## 7. Engineering review checklist (accept/reject gate)

Use this before accepting family/checkpoints:

- Family classification aligns with bracket/thin-extrude style workflow
- Feature targets grounded against real names (for this sample: `@Base-Extrude-Thin`, `@Sketch2`)
- Print constraints explicitly present in assumptions and brief
- At least one remediation note exists for unsupported tools or low-confidence steps

## 8. Button-by-button accounting (tested path)

The table below reflects the validated sequence executed against the running backend.

| UI Control | Endpoint | Expected Result | Run Status |
|---|---|---|---|
| New Design / workflow select | `POST /api/ui/workflow/select` | `workflow_mode = new_design` | PASS |
| Approve Brief | `POST /api/ui/brief/approve` | `latest_message = Brief accepted.` | PASS |
| Save Preferences (Local Gemma) | `POST /api/ui/preferences/update` | `model_provider = local`, Gemma model persisted | PASS |
| Attach Local Path | `POST /api/ui/model/connect` | active model attached + feature count reported | PASS |
| Refresh 3D | `POST /api/ui/preview/refresh` | `Preview refreshed (...)` + PNG/GLB URLs | PASS |
| Auto-Detect Local Model | `GET /api/ui/local-model/probe` | recommended local model + endpoint returned | PASS |
| Refresh Clarifications | `POST /api/ui/clarify` | normalized brief / questions updated | PASS (local Gemma path) |
| Inspect More | `POST /api/ui/family/inspect` | family/confidence/checkpoints updated | PASS (local Gemma path) |
| Accept Family | `POST /api/ui/family/accept` | accepted family persisted | PASS |
| Execute Next Checkpoint | `POST /api/ui/checkpoints/execute-next` | next row status update (executed/failed/mocked) | PASS (mixed by tool support) |
| Run Diff + Reconcile | `POST /api/ui/manual-sync/reconcile` | change summary after snapshots | PASS |
| Save Context | `POST /api/ui/context/save` | snapshot JSON persisted | PASS |
| Load Context | `POST /api/ui/context/load` | state hydrated from saved context | PASS |

## 9. Mocked / partial features and safe operator path

From current refactor assessment and observed runtime behavior:

- `check_interference` in checkpoint execution is still marked `MOCKED` in some flows.
- Some advanced planning actions depend on LLM health and provider config.
- RAG startup may skip vector ingest if `faiss-cpu` is not installed.

Operator-safe approach:

1. Use Clarify + Inspect for planning only after local model probe succeeds.
2. Treat checkpoint tools as staged execution; if a tool is mocked, continue with manual SolidWorks operation and then run manual reconcile.
3. Keep feature targets grounded to actual tree names before execution.

## 10. Preview bug fix included in this run

Issue addressed:

- Preview could export from the wrong active document if target model reopen failed silently.

Fix now applied:

- Preview refresh enforces successful `open_model(...)` before PNG/GLB export.
- If target path is missing or reopen fails, refresh now returns explicit failure instead of silently exporting the currently active document.
- Refresh now requires an attached `active_model_path`; if none is persisted, preview refresh fails with an actionable message instead of exporting an arbitrary active SolidWorks window.

This prevents stale/wrong model screenshots when multiple documents are open in SolidWorks.

For the bracket artifact flow specifically, screenshots are expected from:

- `docs/getting-started/tutorial-parts/u_bracket_from_prompt.sldprt`

and not from temporary `PartXXX` documents.

## 11. Step-by-step operator flow (recommended)

1. Start backend and Prefab UI.
2. Click **New Design**.
3. Paste the Design goal and Assumptions from sections 5 and 6.
4. Set local provider settings and run **Auto-Detect Local Model**.
5. Click **Save Preferences**.
6. Set model path to:

   `C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\bracket.sldprt`

7. Set feature targets:

   `@Base-Extrude-Thin,@Sketch2`

8. Click **Attach Local Path**.
9. Click **Refresh 3D** and verify isometric/front/top/right previews.
10. Click **Refresh Clarifications** then **Inspect More**.
11. Review engineering signals and warnings.
12. Click **Accept Family**.
13. Click **Execute Next Checkpoint** step-by-step; reconcile manual edits when required.
14. Save context snapshot for reproducibility.

## 12. From-scratch reconstruction intent (what to ask the planner)

When you want strict from-scratch execution planning, add this instruction to the design goal:

> Generate a checkpoint sequence that reconstructs the bracket from an empty part using named sketch phases matching Sketch1, Base-Extrude-Thin, and Sketch2-style refinement. Include printability checks for PETG (0.6 nozzle, 0.2 layers) and enforce 1.0 mm clearance constraints in mating regions.

This keeps the generated plan aligned with feature-tree evidence while remaining manufacturable.

## 13. Strict multi-part reconstruction pass (executed transcript)

The following pass was executed against the running backend on localhost to validate call sequencing and result handling across multiple U-Joint files.

### 13.1 Sequence used

1. `POST /api/ui/workflow/select` (`new_design`)
2. `POST /api/ui/brief/approve`
3. `POST /api/ui/preferences/update` (local Gemma)
4. For each file: `POST /api/ui/model/connect` then `POST /api/ui/preview/refresh`
5. `POST /api/ui/clarify`
6. `POST /api/ui/family/inspect`
7. `POST /api/ui/family/accept`
8. `POST /api/ui/checkpoints/execute-next` (4 times)
9. `POST /api/ui/manual-sync/reconcile`
10. `POST /api/ui/context/save`

### 13.2 Captured outcomes (exact-style excerpt)

| Step | Captured result |
|---|---|
| `model/connect:bracket.sldprt` | Attached model: bracket.sldprt, feature tree populated, target grounding available for bracket-like names |
| `model/connect:Yoke_male.sldprt` | Attached model with feature tree, target grounding became partial for bracket-specific refs |
| `model/connect:Yoke_female.sldprt` | Attached model with feature tree, target grounding partial/missing for bracket refs |
| `model/connect:spider.sldprt` | Attached model with feature tree, bracket refs mostly missing |
| `model/connect:pin.sldprt` | Attached model pin.sldprt; type unknown; features 18; target status partially grounded (`@Sketch1`) and missing `@Base-Extrude-Thin,@Sketch2` |
| `model/connect:UJoint.SLDASM` | Attached model UJoint.SLDASM; type unknown; features 22; target status no matching `@Sketch1,@Base-Extrude-Thin,@Sketch2` |
| `preview/refresh:*` | Preview refreshed with GLB + PNG export path; orientation thumbnails generated |
| `clarify` | Generated explicit follow-ups including: exact bracket L/W/H dimensions, mounting geometry details, and chamfer/draft needs |
| `family/inspect` | Family returned `unknown`, confidence `low`, with warnings about missing target matches in assembly context |
| `checkpoints/execute-next` | Repeated failure at checkpoint 1: `create_sketch` and `add_line` failed (`No active model` / `No active sketch`) in this pass context |
| `manual-sync/reconcile` | Returned manual change detection guidance |

### 13.3 What this transcript proves

- Multi-part attach/preview flows are operational and auditable.
- Exact-dimension prompting produces concrete clarification questions instead of vague planning.
- Feature-target grounding must be part-specific (`@Base-Extrude-Thin,@Sketch2` is valid for bracket, not for all U-Joint components).
- Checkpoint execution remains environment/tooling-dependent; failures are surfaced explicitly and do not silently pass.

---

## 14. Beginner guide: build the bracket piece-by-piece using prompts

This section is for first-time users who want to type prompts step-by-step and see what each button does before wiring up the full run from Section 11.

### 14.1 Prerequisites: what must be running

Start two terminals before anything else.

**Terminal A — backend:**

```powershell
.\.venv\Scripts\python.exe -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port 8766
```

Look for this line before continuing:

```
INFO:     Application startup complete.
```

**Terminal B — Prefab UI:**

```powershell
.\.venv\Scripts\prefab.exe serve src/solidworks_mcp/ui/prefab_dashboard.py
```

Then open: [http://localhost:5175](http://localhost:5175)

> **What if the UI port is different?** Prefab prints the actual URL; look for `Serving on http://localhost:XXXX` in Terminal B and use that.

---

### 14.2 Phase 1: Start a new design

**Step 1 — Click "New Design"**

This resets any prior session so you start clean. You will see all fields clear.

What it does internally: calls `POST /api/ui/workflow/select` with `{"workflow_mode": "new_design"}`.

**Step 2 — Paste your design goal**

In the **Design goal** textbox, paste this exact prompt:

> Start from a blank part and create a PETG U-bracket using explicit dimensions only (do not infer hidden dimensions from existing features): overall envelope 78 mm (X) x 52 mm (Y) x 36 mm (Z). Use wall thickness 1.8 mm minimum and target 2.4 mm on load paths (multiples of a 0.6 mm nozzle). Sketch1 must define the base profile with an outer rectangle 78 x 52 mm, inner clearance window 60 x 34 mm centered, and 9 mm corner fillets on the outer corners. Create a thin/base extrusion to 36 mm height with 2.4 mm wall thickness. Sketch2 must add mounting refinements: two M4 reference holes on the flange centerline at X offsets +/-24 mm, hole pilot diameter 4.2 mm, and one cable slot 16 x 8 mm centered on the inner face. Enforce 1.0 mm mating clearance budget where interfaces move or mate. Then compare this from-scratch geometry against U-Joint bracket guidance (feature-tree names and proportions) and report any dimensional mismatch before executing irreversible steps.

In the **Assumptions** textbox, paste:

> Material PETG. Layer height 0.2 mm. Nozzle 0.6 mm. Clearance/tolerance budget 1.0 mm for mating interfaces. Prefer ribs/fillets over sharp stress risers. Avoid long unsupported bridges. Keep feature naming stable for downstream checkpoint targeting.

> **Why these exact prompts?** Explicit dimensions force the LLM to output concrete tool-call arguments (like `width=78.0`) instead of vague descriptions. The planner then generates checkpoints whose progress you can audit.

**Step 3 — Click "Approve Brief"**

You should see a green confirmation in the message area:

```
Brief accepted.
```

What it does: calls `POST /api/ui/brief/approve`. If you see an error here, check that Terminal A is still running.

---

### 14.3 Phase 2: Configure your local AI model

Skip this phase if you have already run Auto-Detect and saved preferences in a prior session.

**Step 4 — Open Model Controls**

Look for the **Model Controls** card in Lane 1. It contains provider and model name fields.

**Step 5 — Click "Auto-Detect Local Model"**

This pings Ollama at `http://127.0.0.1:11434/v1` and detects the best available model.

Expected result in the response area:

```json
{
  "recommended_model": "local:gemma4:e2b",
  "local_endpoint": "http://127.0.0.1:11434/v1"
}
```

The model name field should auto-populate.

> **What if nothing appears?** Ollama may not be running. In a new terminal, run `ollama list`. If you get an error, start Ollama with `ollama serve`. If gemma4 is not listed, pull it with `ollama pull gemma4:e2b`.

**Step 6 — Click "Save Preferences"**

Persists the local endpoint and model name to the session database. You will see:

```
Preferences saved.
```

What it does: calls `POST /api/ui/preferences/update`.

---

### 14.4 Phase 3: Attach a reference model (optional but recommended)

Attaching `bracket.sldprt` gives the LLM real feature-tree evidence to ground its plan.

**Step 7 — Set the model path**

In the **Model path** field, type or paste:

```
C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\bracket.sldprt
```

**Step 8 — Set feature targets**

In the **Feature targets** field, type:

```
@Base-Extrude-Thin,@Sketch2
```

**Step 9 — Click "Attach Local Path"**

Expected response:

```
Attached model: bracket.sldprt
Features: 3
Target status: fully grounded
```

> **What if target status shows "partially grounded" or "missing"?** Check the feature names. If you attached a different part (e.g. `Yoke_male.sldprt`), its feature tree will not have `Base-Extrude-Thin`. Either use `bracket.sldprt` or clear the target field.

**Step 10 — Click "Refresh 3D"**

This exports isometric, front, top, and right view previews. You should see thumbnail images appear.

> **What if "Refresh 3D" shows an error?** SolidWorks may not be running. The preview endpoint tries to open the part in SolidWorks and export PNG. If SolidWorks is not available, the export fails. You can skip preview and continue — Clarify and Inspect still work without a 3D preview.

---

### 14.5 Phase 4: Ask the AI questions (Lane 2)

These two buttons are always visible (no env var required).

**Step 11 — Click "Refresh Clarifications"**

The LLM reads your design goal and returns specific questions it needs answered before planning.

Expected output in the **Clarifying questions** text area (example):

```
1. What is the exact mounting bolt pattern — 2-hole or 4-hole? Confirm M4 pilot diameter is 4.2 mm.
2. Is the cable slot centered on the long axis (Y) or short axis (X) of the inner face?
3. Are corner fillets on the inner window also required, or only on the outer corners?
4. Confirm: 1.0 mm clearance budget applies only to mating faces, not to sketch fillets.
```

> **What if the Clarifying questions area stays empty or shows "N/A"?** The LLM call failed silently. Check that "Save Preferences" was clicked in Phase 2. Also confirm Ollama is running and the model name field shows `local:gemma4:e2b`. The error detail usually appears in the red Badge below the Textarea — look for a message like `Model routing failed`.

**Step 12 — Type your answers**

In the **Answer** textarea, type answers to the questions. Example:

```
1. Two-hole pattern, M4 pilot 4.2 mm, countersink not needed for this run.
2. Cable slot centered on Y-axis of the inner face.
3. Inner window corners: square for now, add fillets in Sketch2 phase if print quality requires.
4. Confirmed: 1.0 mm budget applies only to mating interfaces, not to fillet geometry.
```

**Step 13 — Click "Refresh Clarifications" again**

With your answers added, the LLM refines the question set. If all questions are answered, it may return:

```
No further clarifications needed. Ready to plan.
```

**Step 14 — Click "Inspect More"**

This runs family classification and generates the initial checkpoint sequence.

Expected output in Lane 2 Engineering Signals:

```
Family: bracket
Confidence: medium
Warnings: [none if bracket.sldprt is attached and grounded]
```

The Checkpoint Plan table in Lane 3 will populate with rows like:

| # | Description | Tool | Status |
|---|---|---|---|
| 1 | Create blank part | create_part | pending |
| 2 | Open sketch plane | create_sketch | pending |
| 3 | Draw base profile | add_rectangle / add_line | pending |
| 4 | Add corner fillets | add_sketch_constraint | pending |
| 5 | Extrude base | create_extrusion | pending |
| 6 | Sketch2: mounting holes | add_circle | pending |
| 7 | Sketch2: cable slot | add_rectangle | pending |
| 8 | Print check | analyze_geometry | pending |

> **What if family shows "unknown" with low confidence?** This usually means no reference model is attached, or the attached model is an assembly instead of the bracket part. Detach the current model, re-attach `bracket.sldprt`, and click Inspect again.

**Step 15 — Click "Accept Approach"**

Once you are satisfied with the family and checkpoint plan, click Accept. The session advances to `planned` status and the plan is locked for execution.

---

### 14.6 Phase 5: Execute checkpoints (requires experimental flag)

> **This phase requires** the environment variable `SOLIDWORKS_UI_EXPERIMENTAL_ORCHESTRATION=1` and a running SolidWorks instance.

**Step 16 — Set the env var and restart**

Stop Terminal A (Ctrl+C), then restart it with:

```powershell
$env:SOLIDWORKS_UI_EXPERIMENTAL_ORCHESTRATION = "1"
.\.venv\Scripts\python.exe -m uvicorn solidworks_mcp.ui.server:app --host 127.0.0.1 --port 8766
```

After restarting you will see:

- The **GO** button appear in Lane 1.
- The **Execute Next Checkpoint** button appear in Lane 3.

**Step 17 — Click "Execute Next Checkpoint"**

This sends the first pending checkpoint to the MCP server. Watch the status column change from `pending` to `executed` or `failed`.

Repeat until all checkpoints are executed.

> **What if a checkpoint fails?** The status row turns red and shows an error message. Common failures:
>
> - `No active model` — SolidWorks closed or the part was not created yet. Reopen SolidWorks, create a blank part manually, then retry.
> - `No active sketch` — `create_sketch` succeeded but `open_sketch` was not called. The MCP adapter may need a retry; click Execute Next Checkpoint again.
> - Tool mocked — Some tools are marked `MOCKED` in the current build. The checkpoint will be marked `mocked` and skipped automatically. Use **Run Diff + Reconcile** to sync the gap.

**Step 18 — Run Diff + Reconcile (if any checkpoints were mocked or failed)**

Click **Run Diff + Reconcile** in Lane 2 after completing your manual SolidWorks steps.

This compares the live feature tree against the checkpoint plan and reports any differences.

---

### 14.7 Phase 6: Save and review

**Step 19 — Click "Save Context"**

Saves a snapshot of the session to disk. Useful if you need to resume later.

**Step 20 — Verify the final part**

In SolidWorks, confirm:

- Feature tree contains `Sketch1`, `Base-Extrude-Thin`, `Sketch2`
- Extrusion height is 36 mm
- M4 pilot holes present at ±24 mm offsets
- Cable slot 16 x 8 mm visible on the inner face
- Wall thickness at 2.4 mm on the main body

---

### 14.8 Quick-reference prompt cheat sheet

| Goal | Where to type | Example |
|---|---|---|
| New design with explicit dimensions | Design goal textbox | `Start from a blank part and create a PETG U-bracket ... 78 x 52 x 36 mm ...` |
| Material and print constraints | Assumptions textbox | `Material PETG. Layer height 0.2 mm. Nozzle 0.6 mm.` |
| Answer clarification questions | Answer textarea in Lane 2 | `Two-hole M4 pattern, cable slot centered on Y axis.` |
| Force from-scratch plan | Design goal (append) | `Generate a checkpoint sequence reconstructing from an empty part using feature names matching Sketch1, Base-Extrude-Thin, Sketch2.` |
| Attach a different reference | Model path field | Full path to any `.sldprt` in the U-Joint sample folder |
| Target specific features | Feature targets field | `@Sketch1,@Base-Extrude-Thin,@Sketch2` |

---

### 14.9 Troubleshooting at a glance

| Symptom | Likely cause | Fix |
|---|---|---|
| "Model routing failed" in Lane 2 | LLM provider not configured | Run Auto-Detect + Save Preferences (Phase 2) |
| Ollama not reachable | Ollama service not started | Run `ollama serve` in a separate terminal |
| Model not found | Gemma not pulled | Run `ollama pull gemma4:e2b` |
| "Brief accepted" not shown | Backend not running | Start Terminal A (Section 14.1) |
| Preview thumbnails missing | SolidWorks not open | Skip preview; Clarify/Inspect still work |
| GO button not visible | Experimental flag not set | Set `SOLIDWORKS_UI_EXPERIMENTAL_ORCHESTRATION=1` and restart backend |
| Checkpoint fails with "No active model" | Part not open in SolidWorks | Open SolidWorks, create a blank part, retry checkpoint |
| Family shows "unknown" low confidence | Wrong model attached | Re-attach `bracket.sldprt` and re-run Inspect |
