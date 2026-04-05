---
mode: ask
description: "Classify an existing SolidWorks model from its real feature tree before planning reconstruction. Use when recreating from an existing part, screenshot, mock-up drawing, or sample model."
---
Run an inspect-classify-delegate pass before planning any reconstruction.

Inputs:
- Target model path: ${input:modelPath:C:/Users/Public/Documents/SOLIDWORKS/SOLIDWORKS 2026/samples/learn/Baseball Bat.SLDPRT}
- User goal: ${input:userGoal:Reconstruct the model faithfully and identify the right MCP vs VBA workflow}
- Extra context: ${input:extraContext:Optional screenshot notes, constraints, or dimensions}

Required workflow:
1. If a model path is provided, open the original file first.
2. Read the active state with:
   - `get_model_info()`
   - `list_features(include_suppressed=True)`
   - `get_mass_properties()`
   - `classify_feature_tree()`
3. Summarize the part family, confidence, evidence, and any warnings.
4. Trace the likely parent-child dependency chain from the feature tree.
5. Decide whether the path is:
   - direct MCP solid modeling
   - VBA-backed advanced part modeling
   - assembly planning
   - drawing workflow
   - insufficient evidence, inspect more
6. Only then propose the next reconstruction steps.

Output requirements:
- Start with `Classification Summary`
- Then `Why This Classification`
- Then `Recommended Workflow`
- Then `Next Concrete Steps`
- If confidence is low, say what additional evidence is needed before building

Rules:
- Do not infer “simple extrude” from silhouette alone if the original file is available.
- If the tree shows sheet metal markers (`Sheet-Metal`, `Base-Flange`, `Edge-Flange`, `Sketched Bend`, `Unfold`, `Fold`), preserve that family in the recommendation.
- If only sketch/profile features are visible, treat the result as provisional and combine it with mass properties and images before committing to a rebuild path.