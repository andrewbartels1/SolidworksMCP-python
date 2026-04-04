# From Screenshot to SolidWorks: The Image-First Reconstruction Workflow

This tutorial shows how to take a screenshot or rendered image of a part — including the sample parts that ship with SolidWorks — and use prompting to recreate it from scratch using the MCP server.

The approach mirrors what an engineer does by eye: look at the shape, describe it in terms the CAD system understands, and build it feature by feature.

> The sample parts used throughout this guide live at:
> `C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\`

---

## The Three-Prompt Pattern

Every reconstruction follows the same shape regardless of part complexity:

```
Prompt 1 — Describe          →  Prompt 2 — Plan             →  Prompt 3 — Build & Test
"What do you see in          →  "Turn that description       →  "Execute each step and
 this image?"                    into an ordered MCP             confirm the result matches
                                 tool sequence."                 the reference image."
```

The image goes into Prompt 1. Everything after that is text. You never need to open the original SolidWorks file to read the feature tree — the eye (and a vision LLM) is enough to get started.

---

## Getting a Reference Image

Before prompting, you need a clear isometric or front-view image of the part.

### Option A — Screenshot from SolidWorks directly

Open the sample part in SolidWorks (`File > Open`), orient the view to isometric (`Ctrl+7`), and press `Print Screen` or use the Snipping Tool. Save as a `.png` or `.jpg`.

### Option B — Export from the MCP server

If the MCP server is running and SolidWorks is open with the file loaded:

```
open_model(file_path=r"C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\Paper Airplane.SLDPRT")
export_image(file_path="paper_airplane_ref.jpg", format_type="jpg")
close_model(save=False)
```

The image is saved to disk and can be dragged into Claude Code or uploaded to any vision-capable chat interface.

### Option C — Use the shipped rendered preview (Windows thumbnail)

Windows generates a preview thumbnail for every `.SLDPRT` file in Explorer. Right-click → `Open with > Photos` to get a clean view without opening SolidWorks.

---

## Prompt 1 — Describe the Geometry

Drag the image into Claude Code (or paste into any vision-capable chat). Then write:

```
Look at this image of a SolidWorks sample part.

Describe:
1. The overall shape (what does it look like from a geometric standpoint?)
2. The primary sketch plane (Top, Front, or Right)
3. The key 2D profile geometry (lines, arcs, ellipses, circles)
4. The main 3D feature (extrude, revolve, sweep, loft, or shell)
5. Approximate dimensions based on what's visible (use millimetres)
6. Any secondary features (fillets, holes, cuts, patterns)

Be precise enough that someone could recreate it using only your description.
```

### Example output for Paper Airplane

```
Shape: Flat, wing-shaped part — looks like a top-view of a paper airplane.
Primary sketch plane: Top
Profile: Closed polygon — three lines forming a symmetric delta wing shape:
  - Nose tip at the right: approximately (80, 0)
  - Left wing tip: approximately (0, 60)
  - Right wing tip: approximately (0, -60)
  - All three meet at the nose and fuselage origin (0, 0)
Main 3D feature: Thin extrusion perpendicular to the Top plane
Depth: ~0.5 mm (paper-thin)
Secondary features: None visible
```

---

## Prompt 2 — Plan the MCP Tool Sequence

Feed the description from Prompt 1 into a second prompt. No image needed here.

```
Based on this part description:

  [paste the description from Prompt 1]

Write the exact sequence of SolidWorks MCP tool calls to recreate this part from scratch.
Rules:
- Use only these plane names exactly: "Front", "Top", "Right"
- All dimensions in millimetres
- Follow dependency order: create_sketch → add geometry → exit_sketch → create feature
- Use named arguments in every call
- If any feature requires a VBA macro (loft, sweep, shell), say so explicitly and write
  the generate_vba_part_modeling call instead

Output the plan as a numbered list of copy-pasteable function calls.
```

### Example output for Paper Airplane

```
1.  create_part(part_name="Paper Airplane")
2.  create_sketch(plane_name="Top")
3.  add_line(start_x=0, start_y=0, end_x=80, end_y=0)        # fuselage spine
4.  add_line(start_x=0, start_y=0, end_x=0, end_y=60)        # left wing root
5.  add_line(start_x=0, start_y=60, end_x=80, end_y=0)       # left wing edge
6.  add_line(start_x=0, start_y=0, end_x=0, end_y=-60)       # right wing root
7.  add_line(start_x=0, start_y=-60, end_x=80, end_y=0)      # right wing edge
8.  exit_sketch()
9.  create_extrusion(sketch_name="Sketch1", depth=0.5)
```

---

## Prompt 3 — Build, Then Verify

Ask Claude Code (or your MCP client) to execute the plan and compare the result to the reference image.

```
Execute the following reconstruction plan using the SolidWorks MCP server.
After each step, confirm the result succeeded before continuing.
If a step fails, stop and show the error.

[paste the numbered plan from Prompt 2]

After completing all steps:
1. export_image(file_path="paper_airplane_gen.jpg", format_type="jpg")
2. Compare this generated image to the reference screenshot I provided earlier.
   State whether it looks like a match (shape, proportions, orientation).
```

### Validating with pixel diff (optional)

For automated testing, use the screenshot comparison utility:

```powershell
.\.venv\Scripts\python.exe src\utils\screenshot_compare.py `
  paper_airplane_ref.jpg `
  paper_airplane_gen.jpg
```

A pixel difference below **5%** at the same camera orientation is the pass criterion.

---

## Full Tutorial: Paper Airplane

This is the simplest model in the sample library. Run through all three prompts.

### Reference image

Open `Paper Airplane.SLDPRT` in SolidWorks or export via the MCP server, then screenshot in isometric view.

### Prompt 1 (describe)

```
[attach paper_airplane.jpg]

What shape is this SolidWorks part? Describe the 2D profile and the main 3D feature,
with approximate dimensions in millimetres.
```

### Prompt 2 (plan)

```
Part: flat delta-wing profile on the Top plane, extruded 0.5 mm.
Nose at (80, 0), left wing tip at (0, 60), right wing tip at (0, -60), origin at (0, 0).

Write the MCP tool call sequence to recreate this.
```

### Prompt 3 (build and test)

```
Using the SolidWorks MCP server, execute:

1. create_part(part_name="Paper Airplane")
2. create_sketch(plane_name="Top")
3. add_line(start_x=0, start_y=0, end_x=80, end_y=0)
4. add_line(start_x=0, start_y=0, end_x=0, end_y=60)
5. add_line(start_x=0, start_y=60, end_x=80, end_y=0)
6. add_line(start_x=0, start_y=0, end_x=0, end_y=-60)
7. add_line(start_x=0, start_y=-60, end_x=80, end_y=0)
8. exit_sketch()
9. create_extrusion(sketch_name="Sketch1", depth=0.5)

Then export_image(file_path="paper_airplane_gen.jpg", format_type="jpg")
and compare to the reference.
```

---

## Full Tutorial: U-Joint Assembly

The U-Joint has 9 parts and is the most instructive assembly example. The image-first approach works by tackling each part individually, then assembling.

### Step 1 — Screenshot each sub-part

From `U-Joint/` in Explorer: `crank-shaft.sldprt`, `spider.sldprt`, `yoke_male.sldprt`, `yoke_female.sldprt`, `pin.sldprt`, `bracket.sldprt`, `crank-arm.sldprt`, `crank-knob.sldprt`.

Open each in SolidWorks and screenshot, or use:

```
open_model(file_path=r"...\U-Joint\crank-shaft.sldprt")
export_image(file_path="crank_shaft_ref.jpg", format_type="jpg")
close_model(save=False)
```

### Step 2 — Describe and plan each part

For the crank shaft (Prompt 1):

```
[attach crank_shaft_ref.jpg]

This is the crank-shaft from the SolidWorks U-Joint sample.
Describe its geometry: what kind of revolve or extrude profile, key dimensions,
any cutouts or features visible.
```

For the crank shaft (Prompt 2):

```
Description: cylindrical shaft ~200mm long, ~12mm diameter, with a hex cross-section
at one end for the crank interface, and a circular bore for the spider pin.

Write the MCP reconstruction sequence.
```

Likely plan:

```
1.  create_part(part_name="crank-shaft")
2.  create_sketch(plane_name="Front")
3.  add_centerline(start_x=0, start_y=0, end_x=200, end_y=0)
4.  add_line(start_x=0, start_y=0, end_x=0, end_y=6)         # shaft radius
5.  add_line(start_x=0, start_y=6, end_x=180, end_y=6)       # shaft body
6.  add_line(start_x=180, start_y=6, end_x=200, end_y=10)    # crank end taper
7.  exit_sketch()
8.  create_revolve(sketch_name="Sketch1", axis_entity="Line1", angle=360.0)
```

### Step 3 — Screenshot the assembled view

Screenshot `UJoint.SLDASM` in isometric view. Then:

```
[attach ujoint_assembly_ref.jpg]

This is the U-Joint assembly. The crank-shaft, spider, yoke_male, and yoke_female
are all visible. Describe the mates: which axes are coincident, which faces are
parallel, and what the rotation constraint looks like.
```

### Step 4 — Build the assembly

```
Using the SolidWorks MCP server, create the U-Joint assembly:

1. create_assembly(assembly_name="UJoint")
2. generate_vba_assembly_insert(component_path=r"...\U-Joint\crank-shaft.sldprt")
3. generate_vba_assembly_insert(component_path=r"...\U-Joint\yoke_male.sldprt")
4. generate_vba_assembly_mates(
     mate_type="coincident",
     entity1="crank-shaft/shaft_axis",
     entity2="yoke_male/bore_axis"
   )
5. generate_vba_assembly_insert(component_path=r"...\U-Joint\spider.sldprt")
6. ... (continue per plan)
```

---

## Tips for Better Prompts

### Give the LLM scale context

```
The part is roughly the size of a playing card (90mm × 60mm × 2mm).
```

Without scale hints, the LLM may guess dimensions that are an order of magnitude off.

### Correct the plan before executing

After Prompt 2 produces the plan, review it against the reference image before sending Prompt 3.
If the wing outline looks wrong, adjust the coordinates and regenerate — it's much faster to fix a plan than to delete a bad feature from SolidWorks.

### Use the reconstructor agent for complex parts

For Tier 3+ parts (shells, lofts, mouse housings), paste the image description into the `solidworks-part-reconstructor` agent in Claude Code and ask for a `ReconstructionPlan` — it will flag VBA boundaries automatically and generate the right `generate_vba_part_modeling` call structure.

```
solidworks-part-reconstructor, reconstruction:

[paste geometry description from Prompt 1]

Generate a ReconstructionPlan JSON.
```

### Log runs to catch failures

```powershell
.\.venv\Scripts\python.exe -m solidworks_mcp.agents.smoke_test `
  --agent-file solidworks-part-reconstructor.agent.md `
  --github-models `
  --schema reconstruction `
  --max-retries-on-recoverable 2 `
  --prompt "Paper Airplane: delta-wing profile on Top plane, extruded 0.5mm. Plan reconstruction."
```

All runs are logged to `.solidworks_mcp/agent_memory.sqlite3` — check the error catalog when a step fails.

---

## Running the Test Suite

After adding a new reconstruction workflow, run the agent tests to confirm nothing regressed:

```powershell
# Fast (no SolidWorks required)
.\dev-commands.ps1 dev-test

# Full (with SolidWorks + live agent calls)
.\dev-commands.ps1 dev-test-full
```

To test just the agent CLI smoke tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_agents_smoke_test_cli.py -v
```

---

## Common Errors and Fixes

| Error | Likely cause | Fix |
|---|---|---|
| `Sketch is still active` | `exit_sketch()` was skipped | Always call `exit_sketch()` before creating a feature |
| `Plane not found: "front"` | Wrong case | Use `"Front"`, `"Top"`, `"Right"` exactly |
| `create_loft is not implemented` | Tool not yet available | Use `generate_vba_part_modeling` + `execute_macro` |
| Extruded depth looks wrong | Units mismatch | Pass > 0.5 values as mm; server auto-normalises |
| Assembly mates don't constrain | Wrong entity name | Check entity names via `list_features` on the part |

---

## Related Pages

- [Sample Models Guide](sample-models-guide.md) — per-model feature sequences and reference prompts
- [Prompting Best Practices](prompting-best-practices.md) — general MCP prompting principles
- [Agents and Testing](../getting-started/agents-and-testing.md) — smoke test harness reference
- [Screenshot Equivalence](screenshot-equivalence.md) — pixel-diff comparison methodology
