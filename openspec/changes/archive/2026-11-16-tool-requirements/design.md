## Context

Issue #79 proposed tags `[Maker]`, `[Standard]`, `[Professional]`,
`[Simulation]` and `[PDM]`. Every adapter call was checked for add-ins and
for features SolidWorks sells only above Standard: none are used. Sheet
metal, Hole Wizard (its sizes come from the Toolbox *data* folder, which
Standard installs; the Toolbox part library is what Professional adds),
configurations, design tables, drawings, BOM tables, interference
detection, materials and the exports are all in Standard. Every live test
ran on SOLIDWORKS Professional for Makers 2026; Standard itself hasn't been
run, and the docs say so.

## Decisions

- **Requirement, not licence.** Three values: `nothing`, `installed`,
  `running`. The licence finding is one sentence in the docs, not a tag.
  When a tool that needs an add-in arrives (Simulation, #78), a fourth
  value names it then.
- **Exceptions-only table** in `tools/requirements.py`, defaulting to
  `running`, so a new tool needs no entry unless it works without
  SolidWorks. Mirrors `support_levels.py`.
- **Tag at registration** in `ToolRegistrar._metadata`, beside the level tag.
- **Docs check** parses the overview's section for backticked tool names
  under two sub-headings and compares them with the table.

The `nothing` tools: the ten `generate_vba_*` tools, `generate_vba_code`,
`compare_templates`, `compare_drawing_versions`, `reset_circuit_breaker`.
The `installed` tools: `discover_solidworks_docs`,
`search_solidworks_api_help`, `lookup_api_method`, `lookup_api_interface`,
`find_related_api_members`, `list_hole_sizes`.

## Risks

- A tool reclassified in code but not in the table: the description check
  covers `installed`; a wrong `nothing` would show as a tool failing with
  SolidWorks closed, which the table makes easy to review.
