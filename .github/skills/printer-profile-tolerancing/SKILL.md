---
name: printer-profile-tolerancing
description: "Use when generating tolerance and clearance guidance based on printer profile inputs (model or build volume, nozzle, material, layer height) for SolidWorks MCP design workflows."
---

# Printer Profile Tolerancing

Use this skill to convert manufacturing context into practical design guidance that an LLM can apply before running SolidWorks MCP tools.

## Inputs
- Printer model OR explicit build volume in mm (X/Y/Z)
- Nozzle diameter (mm)
- Material (PLA/PETG/ABS/ASA/Nylon/Resin)
- Layer height (mm)
- Fit/joint type (press fit, sliding fit, snap fit, hinge, clip)

## Outputs
1. Assumptions and constraints (explicit)
2. Recommended tolerance and clearance ranges by feature type
3. Orientation recommendation (bed face and why)
4. Build-volume fit check and split strategy if needed
5. Risk checklist (warping, weak axis, support scarring, overhangs)

## Workflow
1. Normalize units to mm.
2. Validate missing inputs and ask targeted clarification.
3. Choose baseline ranges by process/material.
4. Adjust ranges using nozzle + layer-height heuristics.
5. Add geometry-specific notes for joints and clips.
6. Include mitigation options with tradeoffs.

## Guardrails
- Never output one universal tolerance value.
- Always include assumptions in plain language.
- Mark high-risk recommendations explicitly.
