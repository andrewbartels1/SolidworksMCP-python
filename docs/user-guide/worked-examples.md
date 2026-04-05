# Worked Examples: SolidWorks MCP + Agent Workflow

This page shows three practical reconstruction examples using the same inspect -> classify -> delegate loop:

1. Read the original model state.
2. Classify the feature family before writing geometry.
3. Build with direct MCP tools only when the family supports it.
4. Compare against mass properties and visual output.
5. Reflect and tighten the next prompt.

## Example 1: Paper Airplane (Feature-Tree Audit)

Source file: `C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\Paper Airplane.SLDPRT`

### Example 1 Stage 1: Read

```python
open_model(file_path="...\\Paper Airplane.SLDPRT")
get_model_info()
list_features(include_suppressed=True)
get_mass_properties()
classify_feature_tree(include_suppressed=True)
```

Observed result:

| Field | Value |
| --- | --- |
| Family | `sheet_metal` |
| Recommended workflow | `vba-sheet-metal` |
| Confidence | `high` |
| Why | Feature tree contains sheet-metal markers and bend/fold style operations |

### Example 1 Stage 2: Plan

```text
Use the feature tree and classifier output as the source of truth.
Do not simplify this into a silhouette-only extrusion.
Generate a dependency-preserving sheet-metal reconstruction strategy and flag VBA boundaries.
```

### Example 1 Stage 3: Build

```text
Use a delegated plan that preserves:
1. Base feature
2. Downstream bend/flange dependencies
3. Any unfold/fold state transitions
```

### Example 1 Stage 4: Compare

| Check | Original | Rebuild target |
| --- | --- | --- |
| Family | `sheet_metal` | `sheet_metal` |
| Dependency order | Base + bends/folds | Same pattern |
| Validation signal | Feature tree first | Mass + image second |

### Example 1 Stage 5: Reflect

| Worked | Change next time |
| --- | --- |
| Classifier blocked wrong direct extrude path | Always classify before geometry planning |
| Audit exposed true root feature | Treat silhouette as secondary evidence |

## Example 2: Baseball Bat (Classifier-Backed Revolve)

Source file: `C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\Baseball Bat.SLDPRT`

### Example 2 Stage 1: Read

```python
open_model(file_path="...\\Baseball Bat.SLDPRT")
get_model_info()
list_features(include_suppressed=True)
get_mass_properties()
classify_feature_tree(include_suppressed=True)
```

Classifier result:

| Field | Value |
| --- | --- |
| Family | `revolve` |
| Recommended workflow | `direct-mcp-revolve` |
| Confidence | `high` |

### Example 2 Stage 2: Plan

```text
Confirm revolve family first.
Create a half-profile sketch with a centerline axis.
Pause for human review before create_revolve.
```

### Example 2 Stage 3: Build

```python
create_part(name="baseball_bat_rebuild")
create_sketch(plane="Front")
add_centerline(x1=0, y1=0, x2=210, y2=0)
# ...add profile lines...
exit_sketch()
create_revolve(sketch_name="Sketch1", axis_entity="Centerline1", angle=360)
```

### Example 2 Stage 4: Compare

| Check | Original | Rebuild |
| --- | --- | --- |
| Family | `revolve` | `revolve` |
| Axis-based profile | Yes | Yes |
| Mass/image sanity | Required | Required |

### Example 2 Stage 5: Reflect

| Worked | Change next time |
| --- | --- |
| Classifier gave safe direct-MCP route | Keep the human review checkpoint before revolve |
| Fast build sequence | Add arc fidelity when supported |

## Example 3: U-Joint Pin (Classifier-Backed Next Sample)

Source file: `C:\Users\Public\Documents\SOLIDWORKS\SOLIDWORKS 2026\samples\learn\U-Joint\pin.sldprt`

### Example 3 Stage 1: Read

```python
open_model(file_path="...\\U-Joint\\pin.sldprt")
get_model_info()
list_features(include_suppressed=True)
get_mass_properties()
classify_feature_tree(include_suppressed=True)
```

Classifier-first decision:

| Field | Value |
| --- | --- |
| Family | expected `revolve` or `advanced_solid` depending on tree |
| Decision gate | If `revolve` -> direct MCP. If `advanced_solid` -> VBA-aware plan |
| Rule | Do not start with assumed cylinder-only geometry |

### Example 3 Stage 2: Plan

```text
Use classifier evidence first.
If family is revolve:
- build a centerline-based half profile and revolve.
If family is advanced_solid:
- emit VBA-backed reconstruction steps and keep direct MCP for only supported features.
```

### Example 3 Stage 3: Build

```python
# Branch A: direct revolve path
create_part(name="ujoint_pin_rebuild")
create_sketch(plane="Front")
add_centerline(x1=0, y1=0, x2=60, y2=0)
# ...profile...
exit_sketch()
create_revolve(sketch_name="Sketch1", axis_entity="Centerline1", angle=360)
```

```text
# Branch B: VBA-aware path
1. Preserve feature-family ordering from list_features.
2. Generate macro-backed steps for unsupported operations.
3. Re-check mass properties and image output after execution.
```

### Example 3 Stage 4: Compare

| Check | Expected |
| --- | --- |
| Family alignment | Rebuild family matches classifier + original tree |
| Build path alignment | Direct MCP only for supported features |
| Validation | Mass properties within tolerance and visual sanity |

### Example 3 Stage 5: Reflect

| Worked | Change next time |
| --- | --- |
| Classifier prevented blind geometry assumptions | Add feature-level dependency notes into the planning prompt |
| Branching plan reduced rework | Keep explicit gate between direct MCP and VBA paths |

## Reusable Template

```python
open_model(file_path="C:\\path\\to\\part.SLDPRT")
get_model_info()
list_features(include_suppressed=True)
get_mass_properties()
classify_feature_tree(include_suppressed=True)

# Decide workflow from classifier:
# - direct-mcp-extrude
# - direct-mcp-revolve
# - vba-sheet-metal
# - vba-advanced-solid
# - assembly-planning
# - drawing-review
```

```text
Prompt pattern:
"Use the attached get_model_info, list_features, get_mass_properties, and
classify_feature_tree outputs as source of truth. Propose only the next
few reconstruction steps, preserve parent-child dependencies, and pause
before the first irreversible feature operation."
```

## Common Failure Modes

| Failure | Root cause | Guardrail |
| --- | --- | --- |
| Wrong family selected | Planned from silhouette only | Always run classifier before planning |
| Correct shape but wrong method | Dependency chain collapsed | Preserve tree order in prompt |
| Tool errors mid-build | Unsupported feature path | Route unsupported families to VBA plan |

## Next Steps

1. Expand U-Joint coverage from pin to yoke and spider with the same classifier gate.
2. Add structured `capture_part_state` records to feed retrieval indexing.
3. Use retrieval evidence snippets directly in planning prompts for provenance.
