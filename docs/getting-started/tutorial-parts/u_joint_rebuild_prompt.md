# U-Joint Rebuild Prompt Pack (Bracket + Parts + Assembly)

Use these prompts in order. They now distinguish between two different bracket targets:

- exact SolidWorks sample parity
- print-optimized PETG variant

Do not mix those targets in one run.

## Prompt 1A: Bracket (exact sample parity)

Create only the bracket part from an empty file and match the SolidWorks sample bracket as closely as possible.

Source model to inspect first:

- `C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\bracket.sldprt`

Rules:

- Inspect the source feature tree before planning or sketching.
- Feature tree must end up exactly: `Sketch1`, `Base-Extrude-Thin`, `Sketch2`, `Cut-Extrude1`.
- `Sketch1` is an open profile, not a closed contour.
- Measured `Sketch1` segment endpoints from the sample are:
  - line: `(0.0, 0.0)` to `(0.0, 82.55)`
  - line: `(0.0, 82.55)` to `(-57.15, 82.55)`
  - line: `(-77.216, 27.494)` to `(-44.45, 0.0)`
  - line: `(-44.45, 0.0)` to `(0.0, 0.0)`
- `Base-Extrude-Thin` uses the sample thin-wall settings, not the print variant settings.
- `Sketch2` must be placed on the top flange face, not the global `Top` plane.
- `Sketch2` must create `Cut-Extrude1` as a blind cut with depth `10.0 mm` downward.
- Match the sample appearance as well as the geometry: same feature order, same hole placement, same overall proportions, same color if appearance metadata is available.
- Do not add extra features beyond the four target items unless the model is invalid without them.
- Screenshot exports must be captured from the rebuilt `u_bracket_from_prompt.sldprt` document, not whichever SolidWorks window is currently active.

Validation output required:

- Report the resulting feature tree in order.
- Report the measured thin-wall value, extrusion depth, and hole diameter from the rebuilt part.
- Report whether `Sketch2` was created on a model face or on a reference plane.
- Report any deviation from the 4-feature target.

## Prompt 1B: Bracket (print-optimized PETG variant)

Create only the bracket part from an empty file and do not copy geometry from any existing model.

Requirements:

- Feature names must be exactly: `Sketch1`, `Base-Extrude-Thin`, `Sketch2`.
- `Sketch1` is an open bent-link profile (top flange, vertical web, bottom rail, angled lead-in tab).
- `Base-Extrude-Thin` uses `1.5 mm` wall thickness and one-direction depth extrusion out of `Sketch1`.
- `Sketch2` adds one mounting hole on the top flange (`4.2 mm` diameter M4 pilot) and cuts through all.
- Keep bend transitions smooth (arc transitions, no sharp internal stress corners).
- Material intent: PETG, `0.2 mm` layer, `0.6 mm` nozzle.
- Do not add extra features beyond `Sketch1`, `Base-Extrude-Thin`, `Sketch2` unless required to fix invalid geometry.

Validation output required:

- Report resulting feature tree in order.
- Report thin-wall value, extrusion depth, and hole diameter.
- Report any deviation from the 3-feature target.

## Prompt 2: Remaining U-Joint part set (single-pass planner)

Create a complete U-joint part plan from scratch for these parts only:

- Yoke_male
- Yoke_female
- Spider
- Pin
- Crank-shaft
- Crank-arm
- Crank-knob
- Bracket

Rules:

- Build each part in its own file from an empty part template.
- Use stable feature names per part: Sketch1, BaseFeature, Sketch2, Refinement1 (or fewer if unnecessary).
- Apply print-aware constraints: PETG, 0.2 mm layer, 0.6 mm nozzle.
- Use 1.0 mm clearance budget only at mating interfaces.
- Prefer symmetric references and datum-driven dimensions to keep assembly constraints robust.
- For cylindrical mating elements (pin/spider bores), report shaft/hole nominals and resulting clearance.
- For `Bracket`, explicitly state whether you are using Prompt `1A` exact-sample parity or Prompt `1B` print-optimized variant.
- Do not infer hidden dimensions from any final sample model unless the selected bracket mode is `1A` exact-sample parity.

Output format:

- For each part, return:
  - part_name
  - ordered_feature_plan
  - critical_dimensions
  - mating_interfaces
  - print_risks_and_mitigations

## Prompt 3: UJoint.SLDASM assembly build

Create assembly UJoint.SLDASM from the generated parts without referencing prebuilt mates.

Assembly rules:

- Insert components with fixed origin strategy: one grounded primary component, all others mated relative to datums.
- Create only deterministic mates (coincident, concentric, distance, angle as required).
- Preserve intended DOF where rotation is required; do not over-constrain the mechanism.
- Validate for interference and report collisions before finalizing.
- Output final mate list with component pair, mate type, and target references.

Validation output required:

- Mate count and status (fully defined / under-defined / over-defined).
- Interference summary.
- Motion sanity statement for the joint.

## Prompt 4: Final QA and parity check

Run a final parity check between generated part/assembly set and the intended U-joint topology.

Checklist:

- All required part files exist.
- Bracket feature tree matches the selected bracket mode:
  - exact sample parity: `Sketch1`, `Base-Extrude-Thin`, `Sketch2`, `Cut-Extrude1`
  - print variant: `Sketch1`, `Base-Extrude-Thin`, `Sketch2`
- Assembly resolves all required components.
- No blocking rebuild errors.
- No unresolved mate references.
- Export isometric PNG for each part and for final assembly.

Return a pass/fail table with actionable corrections for each failed line item.

## How To Use This Pack In The Prefab UI

1. Start with Prompt 1A *or* Prompt 1B (never both in one session).
2. After bracket completion, run Prompt 2 to plan remaining parts.
3. Run Prompt 3 to build `UJoint.SLDASM` from generated parts.
4. Run Prompt 4 and fix any failed checklist lines before export.

### Bracket Artifact Script (Prompt 1A parity helper)

Reference script:

- `docs/getting-started/tutorial-parts/build_u_bracket_artifact.py`

Current parity settings implemented in the script:

- `Base-Extrude-Thin` depth: `38.1 mm`
- thin wall: `6.35 mm`
- thin feature auto-fillet corners: enabled
- thin feature fillet radius: `3.175 mm`
- hole diameter: `12.70 mm`
- hole center offset: `19.05 mm` from the right edge reference (centerline-driven)
- `Cut-Extrude1` depth: blind `10.0 mm` (downward)
- end-of-run document state: closes stray documents and restores only `u_bracket_from_prompt.sldprt` as the active model

Run from repository root:

```powershell
.\.venv\Scripts\python.exe docs/getting-started/tutorial-parts/build_u_bracket_artifact.py
```

Expected outputs:

- `docs/getting-started/tutorial-parts/u_bracket_from_prompt.sldprt`
- `docs/getting-started/tutorial-parts/u_bracket_from_prompt_isometric.png`
- `docs/getting-started/tutorial-parts/answer_key_bracket_isometric.png`

### Annotated screenshot references (Prompt 1A review)

- Rebuilt bracket image: `docs/getting-started/tutorial-parts/u_bracket_from_prompt_isometric.png`
- Sample answer key image: `docs/getting-started/tutorial-parts/answer_key_bracket_isometric.png`
- Review checklist overlay items:
  - top flange hole on the same face as the sample reference
  - blind cut depth of `10.0 mm`
  - feature order `Sketch1 -> Base-Extrude-Thin -> Sketch2 -> Cut-Extrude1`
