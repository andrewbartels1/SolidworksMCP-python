# SolidWorks as Code (SoC)

SolidWorks as Code lets you record an interactive MCP session and export it as a clean, runnable Python script.  The round-trip is:

```text
MCP tool calls  →  SQLite log  →  soc_exporter  →  script.py
                                                  ↕  rewind / pickup
```

Every call you make through the MCP adapter is logged.  When you're done, export the log as a self-contained script.  You can rewind to any checkpoint and replay, or pick up manual changes made directly in SolidWorks.

---

## 1. Quick start

### Enable logging on a session

```python
from solidworks_mcp.adapters.circuit_breaker import CircuitBreakerAdapter

adapter = CircuitBreakerAdapter(...)
adapter.soc_session_id = "my-bracket"      # any unique string
# adapter.soc_db_path = Path("custom.db")  # optional override
```

Every adapter call from this point is written to SQLite as a `ToolCallRecord`.

### Export to a script

```python
from solidworks_mcp.agents.soc_exporter import export_session

export_session("my-bracket", "my_bracket.py")
```

Or from the command line:

```sh
python -m solidworks_mcp.agents.soc_exporter my-bracket my_bracket.py
```

The exported script looks exactly like the hand-written reference artifact `build_u_bracket_artifact.py`.  You can open it, read it, and run it to reproduce the part from scratch.

---

## 2. Checkpoints

A **checkpoint** marks a save point: the model file path, the record range that produced it, and a label you choose.

### Create a checkpoint (in a live session)

```python
await adapter.soc_create_checkpoint(
    "base-extrude",
    "C:/parts/bracket_cp1.sldprt",
)
```

This writes a `SoCCheckpoint` row to SQLite and inserts a parseable comment block into the exported script:

```python
        # -- checkpoint ----------------------------------------------------
        # label:    base-extrude
        # file:     C:/parts/bracket_cp1.sldprt
        # records:  1-6
        # ----------------------------------------------------
```

### List checkpoints

```python
from solidworks_mcp.agents.soc_rewind import list_checkpoints

for cp in list_checkpoints("my-bracket"):
    print(cp["label"], cp["file_path"])
```

---

## 3. Rewind

Rewind opens the `.sldprt` saved at a checkpoint and optionally truncates the script to that boundary.

```python
from solidworks_mcp.agents.soc_rewind import rewind_to_checkpoint

script = open("my_bracket.py").read()
truncated = await rewind_to_checkpoint(
    adapter,
    session_id="my-bracket",
    label="base-extrude",
    script_text=script,
)
# truncated is the script up to (and including) the checkpoint block.
# Continue building by appending new tool calls.
```

CLI (prints checkpoint info):

```sh
python -m solidworks_mcp.agents.soc_rewind my-bracket base-extrude
```

---

## 4. Pickup (reverse-engineer manual changes)

If you make changes directly in SolidWorks after the last checkpoint, `pickup_changes` diffs the current feature tree against the last snapshot and emits delta lines.

```python
from solidworks_mcp.agents.soc_pickup import pickup_changes

delta_lines = await pickup_changes(
    adapter,
    session_id="my-bracket",
    checkpoint_label="post-manual-edit",
    output_path="my_bracket.py",   # appended before the finally block
)
```

Delta output example:

```python
        # ── pickup ──────────────────────────────────────────────
        # 1 new feature(s) detected since last checkpoint
        # Fill in '?' placeholders before running.
        # ──────────────────────────────────────────────────────────

        # [pickup] 'Fillet1' (fillet)
        require(
            await adapter.add_fillet(radius=?, edge_names=[]),  # TODO: radius + edges
            "add_fillet Fillet1",
        )
```

---

## 5. How the exporter handles every tool call

The exporter has two layers:

| Layer | What it does |
| --- | --- |
| **Specialized emitters** | Tracks entity IDs returned by `add_line`, `add_circle`, etc. and emits them as named Python variables (`line_1`, `circle_1`) so constraints/dimensions can reference them by name. |
| **Generic fallback** | Every other logged write call is emitted as `require(await adapter.<tool_name>(**kwargs), "<tool_name>")` directly from the logged `input_json` — no manual wiring needed. |

Read-only queries (`get_model_info`, `list_features`, `get_dimension`, etc.) are **logged to SQLite** for audit but **skipped in the replay script** since they don't change model state.

---

## 6. Interactive session walkthrough

This section shows the **full loop**: how you drive MCP interactively, place checkpoints, export the generated script, and rewind when something goes wrong.  The Yoke_male part from the U-joint assembly serves as the example.

### 6.1 Start a session

Tell Claude Code to tag all calls with a session ID before doing anything else:

```text
Use session_id "ujoint-yoke-male" for this session.
Build Yoke_male.sldprt for the U-joint assembly from these dimensions only:

  Profile      : U-shape on Front plane, 80 mm wide × 100 mm tall
                 Body zone  Y =  0 → 40 mm  (40 mm body, full width)
                 Arm zone   Y = 40 → 100 mm  (60 mm arms, 15 mm wide each)
                 Arm gap    X = -25 → +25    (50 mm clear span)
  Depth        : 38 mm symmetric extrude (±19 mm from Front plane)
  Pin bores    : ∅8 mm in each arm, centred at X = ±32.5 mm, Y = 70 mm
  Flange pad   : ∅60 mm × 3 mm, extruded downward from the body base
  Flange holes : 4 × ∅4.2 mm on ∅50 mm bolt circle (M4 clearance)
  Arm fillets  : 1 mm on arm top corners

After each major phase, create a checkpoint to save a restore point.
Do NOT open the reference file (Yoke_male.sldprt) yet — compare at the end.
```

Behind the scenes, Claude Code sets `adapter.soc_session_id = "ujoint-yoke-male"` and every subsequent MCP call is written as a `ToolCallRecord` to `.solidworks_mcp/agent_memory.sqlite3`.

---

### 6.2 Phase 1 — U-body extrude

Claude calls the MCP tools to draw the 8-line U-profile and extrude it.  You watch the part build live in SolidWorks.  When it looks right, prompt:

```text
Looks good — the U-profile is extruded cleanly.
Create a checkpoint labelled "body-extrude" and save the file as
docs/getting-started/tutorial-parts/yoke_male_cp1.sldprt
```

Claude calls:

```python
await adapter.save_file("...yoke_male_cp1.sldprt")
await adapter.soc_create_checkpoint("body-extrude", "...yoke_male_cp1.sldprt")
```

SQLite now has a `SoCCheckpoint` row pointing to that file and spanning records 1–12.

**Export mid-session to check the script so far:**

```powershell
.venv\Scripts\python.exe -m solidworks_mcp.agents.soc_exporter `
    ujoint-yoke-male yoke_male_draft.py
```

The output script looks like this — the exporter generated it entirely from the SQLite log, no hand-writing:

```python
        require(await adapter.create_part(name='yoke_male'), "create_part")

        require(await adapter.create_sketch('Front'), "create_sketch")

        line_1 = require(await adapter.add_line(-40.0, 0.0, -40.0, 100.0), "add_line")
        line_2 = require(await adapter.add_line(-40.0, 100.0, -25.0, 100.0), "add_line")
        line_3 = require(await adapter.add_line(-25.0, 100.0, -25.0, 40.0), "add_line")
        line_4 = require(await adapter.add_line(-25.0, 40.0, 25.0, 40.0), "add_line")
        line_5 = require(await adapter.add_line(25.0, 40.0, 25.0, 100.0), "add_line")
        line_6 = require(await adapter.add_line(25.0, 100.0, 40.0, 100.0), "add_line")
        line_7 = require(await adapter.add_line(40.0, 100.0, 40.0, 0.0), "add_line")
        line_8 = require(await adapter.add_line(40.0, 0.0, -40.0, 0.0), "add_line")

        require(await adapter.exit_sketch(), "exit_sketch")

        require(
            await adapter.create_extrusion(
                ExtrusionParameters(
                    depth=38.0,
                    both_directions=True,
                )
            ),
            "create_extrusion",
        )

        require(await adapter.save_file('...yoke_male_cp1.sldprt'), "save_file")

        # -- checkpoint ----------------------------------------------------
        # label:    body-extrude
        # file:     yoke_male_cp1.sldprt
        # records:  1-12
        # ----------------------------------------------------
```

Notice what's happening:

- `add_line` calls are **specialized**: each gets its own variable (`line_1`, `line_2`…) because later constraint calls would need to reference them by name.
- `create_extrusion` falls through to the **specialized emitter** which formats `ExtrusionParameters` cleanly.
- `add_fillet` (added later) falls through to **`emit_generic`** — no manual wiring at all.
- `list_features` or `get_model_info` calls you made to check the part are **silently skipped** — they're logged for audit but they don't belong in a replay script.

---

### 6.3 Rewind example — bore diameter was wrong

Suppose after Phase 2 (bore cut) you realise the bore was ∅10 mm instead of ∅8 mm.  The bore checkpoint is `bore-cut`.  Tell Claude:

```text
The bore diameter is wrong — it came out ∅10 mm, should be ∅8 mm (radius 4 mm).
Rewind to the "body-extrude" checkpoint and redo the bore.
```

Claude runs:

```python
from solidworks_mcp.agents.soc_rewind import rewind_to_checkpoint

script = open("yoke_male_draft.py").read()
truncated = await rewind_to_checkpoint(
    adapter,
    session_id="ujoint-yoke-male",
    label="body-extrude",
    script_text=script,
)
```

What happens:

1. `yoke_male_cp1.sldprt` (the body-extrude checkpoint file) is opened in SolidWorks.
2. `truncated` is the script with everything after `body-extrude` removed — a clean slate.
3. Claude then redo the bore sketch with `radius=4.0` and creates a new `bore-cut` checkpoint.

From the command line (prints checkpoint info, no SolidWorks needed):

```sh
python -m solidworks_mcp.agents.soc_rewind ujoint-yoke-male body-extrude
# Checkpoint: body-extrude
#   file:     .../yoke_male_cp1.sldprt
#   records:  1-12
#   created:  2026-05-15T14:22:03+00:00
#
# To rewind: open '.../yoke_male_cp1.sldprt' in SolidWorks
```

---

### 6.4 Phase 3 — flange, holes, fillets

Continue prompting Claude:

```text
Good. Now add the flange pad: ∅60 mm circle on the Front plane at Y=0,
extruded 3 mm downward. Then 4 × ∅4.2 mm holes on the Top plane at
(±25, 0) and (0, ±25). Finally, 1 mm fillet on the arm top corners.
Create a checkpoint "final" and save as yoke_male_final.sldprt.
```

Claude calls `create_extrusion`, `create_cut_extrude`, `add_fillet`, `save_file`, `soc_create_checkpoint` in sequence.  Each call is logged.

---

### 6.5 Final export and regression test

Export the finished session:

```powershell
.venv\Scripts\python.exe -m solidworks_mcp.agents.soc_exporter `
    ujoint-yoke-male docs/getting-started/tutorial-parts/yoke_male_generated.py
```

The complete generated script is the source of truth for this part.  Run it on a clean SolidWorks session to confirm it's fully reproducible:

```powershell
.venv\Scripts\python.exe docs/getting-started/tutorial-parts/yoke_male_generated.py
```

If it completes without error and the exported PNGs match the reference:

```text
C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\Yoke_male.sldprt
```

...the part is done.  Commit the generated script as the build artifact.

The hand-authored reference version lives at [`tutorial-parts/build_yoke_male_runbook.py`](tutorial-parts/build_yoke_male_runbook.py) and shows the identical structure.

---

### 6.6 Summary: when to place a checkpoint

| Trigger | Checkpoint label convention |
| --- | --- |
| Main body mass looks right in SolidWorks | `body-extrude` |
| Each major cut / hole feature complete | `bore-cut`, `flange-holes` |
| Ready to start a risky feature (sweep, loft, shell) | `pre-<feature>` |
| Part visually verified against reference image | `verified` |
| Assembled mate added and confirmed | `mate-<part>` |

Place checkpoints **before** you're sure things are right — the cost is a saved file and one SQLite row; the benefit is a clean rewind target if the next step breaks something.

---

## 7. Tutorial: U-bracket from a design spec

The script [`tutorial-parts/build_u_bracket_runbook.py`](tutorial-parts/build_u_bracket_runbook.py) builds a cable-routing U-bracket entirely from the design spec below — no reference model used during construction.

**Spec** (from the original Prefab UI runbook):

| Parameter | Value |
| --- | --- |
| Outer envelope | 78 mm (X) × 52 mm (Y) × 36 mm (Z) |
| Inner clearance | 60 mm × 34 mm (9 mm walls on all sides) |
| Corner fillets | 9 mm radius on outer vertical edges |
| Mounting holes | M4 pilot 4.2 mm dia, X = ±24 mm on top flange |
| Cable slot | 16 mm × 8 mm, centred on top flange |
| Material / print | PETG, 0.6 mm nozzle, 0.2 mm layers |

**Run it** (requires SolidWorks + MCP server running):

```powershell
.\.venv\Scripts\python.exe docs/getting-started/tutorial-parts/build_u_bracket_runbook.py
```

**Verify** by comparing the exported PNGs against `bracket.sldprt`:

```text
C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\bracket.sldprt
```

### What the script demonstrates

1. **Two concentric rectangles** in Sketch1 → SolidWorks extrudes the annular region automatically, producing the 9 mm walls.
2. **`create_extrusion`** emits the `ExtrusionParameters` block exactly as the exporter would generate it.
3. **`add_fillet`** falls through to `emit_generic` — no specialized emitter needed.
4. **Two checkpoints** with parseable comment blocks, readable by `soc_rewind.truncate_script_at`.
5. **Sketch 2** adds mounting features on the top flange; face selection note shows where a production script would reference an actual model face.

---

## 7. API reference

| Module | Key function |
| --- | --- |
| `soc_exporter` | `export_session(session_id, output_path)` |
| `soc_exporter` | `generate_script(records, checkpoints=...)` |
| `soc_rewind` | `rewind_to_checkpoint(adapter, session_id, label)` |
| `soc_rewind` | `truncate_script_at(script_text, label)` |
| `soc_pickup` | `pickup_changes(adapter, session_id, checkpoint_label=...)` |
| `history_db` | `list_soc_checkpoints(session_id)` |
| `history_db` | `get_soc_checkpoint(session_id, label)` |

---

## 8. Planned improvements

- **Issue [#21](https://github.com/andrewbartels1/SolidworksMCP-python/issues/21)** — Assembly-aware `list_features`: traverse sub-components in `.SLDASM` and list features per part.
- **Issue [#22](https://github.com/andrewbartels1/SolidworksMCP-python/issues/22)** — Context and glossary injection engine: TAG-style domain context for MCP tool calls (inspired by [this article](https://towardsdatascience.com/rag-isnt-enough-i-built-the-missing-context-layer-that-makes-llm-systems-work/)).
- **Phase 3** — Lightweight two-panel UI: Monaco script editor (left) + Three.js GLB viewer (right) with checkpoint timeline.
