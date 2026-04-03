---
mode: ask
description: "Generate a docs demo page for SolidWorks MCP tools using a reproducible sample-model workflow."
---
Create or update a documentation page for a SolidWorks MCP demo.

Inputs:
- Demo title: ${input:demoTitle:Example bracket workflow}
- Audience: ${input:audience:SolidWorks users new to LLM agent workflows}
- Sample model path: ${input:samplePath:C:/Users/Public/Documents/SOLIDWORKS/SOLIDWORKS 2026/samples/learn}
- Primary tools: ${input:tools:create_part,create_sketch,create_extrusion}
- Expected outputs: ${input:outputs:part file, validation notes, screenshot}

Requirements:
1. Include prerequisites and environment notes.
2. Include exact step-by-step MCP tool sequence.
3. Include at least 3 troubleshooting cases tied to likely failures.
4. Include expected output verification checkpoints.
5. Keep examples copy/paste-friendly.
