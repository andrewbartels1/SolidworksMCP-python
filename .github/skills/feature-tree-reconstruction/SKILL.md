---
name: feature-tree-reconstruction
description: "Use when reconstructing an existing SolidWorks model and you need inspect-classify-delegate routing with evidence, confidence, and safe execution checkpoints. Trigger phrases: reconstruction, reverse engineering, feature tree, classify family, inspect-classify-delegate, list_features, classify_feature_tree, sheet metal, VBA fallback."
---

# Feature-Tree Reconstruction

Use this skill when the original model is available and appearance-first guessing would be risky.

## Objective

Produce a safe, evidence-backed reconstruction workflow that starts from model inspection and only executes after the family and first-feature strategy are approved.

## Workflow

1. Inspect before planning:
   - `open_model`
   - `get_model_info`
   - `list_features(include_suppressed=True)`
   - `get_mass_properties`
   - `classify_feature_tree`
2. Classify feature family and confidence:
   - `revolve`, `extrude`, `sheet_metal`, `advanced_solid`, `assembly`, `drawing`, `unknown`
3. Delegate by family:
   - `sheet_metal` and unsupported advanced families: VBA-aware reconstruction path
   - simple part families: direct MCP checkpoint plan
   - assembly: component-first decomposition, part-level reconstruction per component
4. Retrieve supporting evidence before execution:
   - local worked examples
   - tool-catalog pages
   - recent error/remediation history
5. Execute conservatively:
   - propose 3-6 checkpoint steps only
   - require human approval before each irreversible step
6. Verify and store:
   - capture resulting feature-family alignment
   - compare mass properties and key dimensions
   - log failures and remediation for future runs

## Output Contract

Always return:

- `family`
- `confidence` (`high`/`medium`/`low`)
- `evidence` (top items used)
- `warnings` (contradictions, missing evidence)
- `recommended_workflow`
- `checkpoint_plan` (3-6 steps)
- `requires_human_confirmation` (true/false)

## Guardrails

- Never reconstruct from silhouette only when the source model is available.
- Never produce a monolithic 20-step build plan before family acceptance.
- Do not continue execution when confidence is low and contradictory evidence exists.
- If family is `unknown`, force additional inspection and user clarification before build.
- For sheet metal and unsupported operations, route to VBA-aware planning instead of guessing direct tool calls.

## Failure Recovery

When a tool fails:

1. Record error type, root cause, and remediation.
2. Roll back to the last accepted checkpoint.
3. Replan only the next checkpoint, not the whole workflow.
4. Surface at least one alternative path with tradeoffs.
