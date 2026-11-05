# Work queue

The order the open issues are taken in. Each item becomes an OpenSpec
change under `openspec/changes/` ("spec, then execute"): its plan is
reviewed, then implemented, signed off live where it touches SolidWorks,
and archived after its PR merges. Update this file when an item is done
or the order changes.

Last updated 2026-11-04.

| # | Item | Issue | OpenSpec change | State |
| --- | --- | --- | --- | --- |
| 1 | Tool descriptions agents can act on: one description standard, MCP hints and family tags, and a check that keeps them | #82 (docstring half) | `tool-descriptions-for-agents` | Plan approved 2026-11-04; three PRs: (1) standard, check and hints, (2) the eight worst-scoring modules, (3) the other six |
| 2 | Guidance through MCP and an installable skill: the server's `instructions`, the skill served as `skill://` resources with FastMCP 3.4.9's `SkillProvider`, and the same skill installable into an agent | #175 | not yet written | Next |
| 3 | `--selftest` command and a compatibility-report issue template | #179 | not yet written | |
| 4 | README: COM API coverage audit and licence-tier tags | #79 | not yet written | |
| 5 | Remove the stale `validate_coverage.py`; decide whether mypy gates CI | #157 | not yet written | |
| 6 | Bracket demo GIF for the README: narrow the issue or close it | #147 | not yet written | |
| 7 | Clear out duplicate and overlapping tools: compare each cluster, keep one, settle a verb list, deprecate old names for one release | #174 | not yet written | Bottom of the queue, by request 2026-11-04 |
| 8 | Optional toolsets or a discovery mode, to cut the tool list's size | #176 | not yet written | After #174, which decides which families are core |

## Notes

- Until #174 lands, item 1's descriptions say which of two overlapping
  tools to use ("For ..., use `other_tool`."), so agents can pick
  correctly before any tool is removed.
- Item 1's family tags are what item 8's toolsets filter on.
- Parked: the intermittent SolidWorks error sound during
  `create_cut_extrude` in the chamfer live tests (#199, #201). Revisit if it
  causes failures; run `live_demo.ps1 -Trace` and read the "The hole cut"
  line.
