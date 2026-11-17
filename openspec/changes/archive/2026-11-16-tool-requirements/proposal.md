## Why

Issue #79's other half asks for licence-tier tags, so people know before
installing whether their SolidWorks licence is enough. Checking every tool
gives a simpler answer than the issue expected: no tool calls an add-in
(Simulation, PDM, Routing, PhotoView) or a feature sold only with
Professional or Premium, so any licence that runs SolidWorks works, Makers
included. What does differ between tools is whether SolidWorks has to be
there at all: 14 tools never touch it, and 6 read its installed files
without it running. A tag per tool for the licence would be the same tag
139 times; a tag for what the tool needs from SolidWorks says something.

## What Changes

- Every tool gets one requirement, kept in one reviewable table like the
  support levels: `nothing` (works with no SolidWorks), `installed` (reads
  SolidWorks' installed files; it doesn't have to be running), or
  `running` (calls the running SolidWorks; the default).
- `ToolRegistrar` adds a `needs:<requirement>` tag to each tool, so a
  client can filter on it.
- The tools overview gets a short section: the licence finding and the
  20 tools that don't need SolidWorks running, by name. A check keeps the
  section and the table the same.
- The README's "Supported Today" gets one line pointing to that section.

## Capabilities

### New Capabilities
- `tools/tool-requirements`: each tool's requirement, its tag, and the
  check that keeps the table, the descriptions and the docs agreeing.

### Modified Capabilities
None.

## Impact

- `src/solidworks_mcp/tools/requirements.py` (new), `tools/tool_boundary.py`.
- `docs/user-guide/tools-overview.md`, `README.md`, `CHANGELOG.md`.
- Tests beside each module. No behaviour change for any tool.
