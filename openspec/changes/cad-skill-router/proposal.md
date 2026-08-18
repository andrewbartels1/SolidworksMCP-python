## Why

This MCP server does exactly one thing today, per its own README: SolidWorks automation - describe intent, generate a plan, execute MCP tools, inspect results, iterate. That stays true after this change; it is not becoming a multi-engine CAD generator. What changes is that an agentic session driving this server can also have *other* CAD-related skills installed alongside it (starting with the external `earthtojake/text-to-cad` skill library) that produce or consume artifacts this server can act on - a brand-new part generated elsewhere as a STEP file, for example. Today there is no structured way for the assistant to recognize when a request calls for one of those external skills instead of (or in addition to) this server's own native tools, or to know what to do with the result once it comes back. Without an explicit routing step, either the LLM has to guess, the tool surface grows unconstrained as more external skills get paired with this server (the source research report, `docs/planning/text-to-cad-cadam-integration-report.md`, is explicit that this makes the LLM worse, not better), or users have to already know which skill to reach for. This change adds the thin routing layer the report recommends: a small, named set of branches - `solidworks-native` (this server's own tool surface, unrestricted), `text-to-cad` (hand off to/from the external `cad` skill via issue #43's STEP import), `mesh-concept` (reserved, no backing implementation yet) - so external skills plug in as bounded, discoverable branches instead of the assistant guessing at an unconstrained tool list. Addresses [issue #42](https://github.com/andrewbartels1/SolidworksMCP-python/issues/42).

## Revision note (2026-08-15): the dashboard/LLM-driven design was replaced

The first implementation of this change (still visible in this file's and design.md's git history) integrated with `src/solidworks_mcp/ui/services/llm_service.py` — a dashboard-only orchestration pipeline that called out to an LLM provider (via pydantic-ai) to classify each request. That whole `src/solidworks_mcp/ui/` module has since been **deleted from the repo** (separate maintainer decision, unrelated to this change's own merits): the dashboard added a second running process, a second LLM API call per classification, and a dependency surface (`fastapi`, `prefab-ui`) this project no longer wants.

This change was rebuilt against that new reality: **no UI, no internal LLM call.** The routing capability is now a plain MCP tool (`get_skill_route` in `src/solidworks_mcp/tools/skill_router.py`) that any MCP client — Claude Code, Claude Desktop, an OpenAI-compatible client via MCP — can call directly. The calling model (already an LLM, already in the loop for the whole session) decides which of the three named families fits, using the tool's own parameter description as its classification guide, then calls the tool with that decision to get back the validated, bounded execution contract. There is no second, nested model call anywhere in this capability.

Everything below describes the *current* (tool-based) design. See git history on this file for the superseded dashboard-integrated version if useful context.

## What Changes

- Add a `get_skill_route` MCP tool (registered via `register_skill_router_tools` in `src/solidworks_mcp/tools/skill_router.py`, following this repo's standard tool-module pattern) that, given a skill family the *calling model* has already selected (`solidworks-native` / `text-to-cad` / `mesh-concept`), returns a bounded execution contract: `allowed_tools`, `validation_steps`, `expected_outputs`, and `fallback`.
- `allowed_tools` is validated against the `SolidWorksAdapter` interface (`src/solidworks_mcp/adapters/base.py`) via plain class introspection at call time, not a hardcoded list — fails closed (excludes) any name that isn't a real adapter capability, so the router can never claim a capability that doesn't exist. (This was originally scoped as an MCP `list_tools()` check against a dashboard-side FastMCP instance that turned out not to exist in that process; see design.md Decision 3 for the reasoning, which still holds even though the caller context has since changed again.)
- The `solidworks-native` branch's `allowed_tools` is the full adapter capability set (every public `SolidWorksAdapter` method) — per design.md Decision 5, no curated subset, since solidworks-native requests already legitimately span the whole existing tool surface with no router in front of them.
- `text-to-cad` and `mesh-concept` branches return an explicit stub route (`allowed_tools: []`, a clear `fallback` message referencing issue #43 or "no backing implementation yet") since neither has a backing implementation. #43 is intentionally sequenced *after* this change specifically so it can populate the real `text-to-cad` branch behind this change's existing tool contract, instead of this change stubbing around a nonexistent one.
- No classification/confidence scoring happens inside this capability — that reasoning now belongs to the calling model, which decides the `family` argument itself before calling the tool. (The dashboard-era design's confidence threshold and low-confidence fallback are superseded by this: an LLM driving an MCP session either knows which family fits, in which case it calls the tool with that family, or it doesn't, in which case it can ask the user — the same judgment call any other tool-use decision already requires, not something this capability needs to re-implement.)

## Capabilities

### New Capabilities
- `agents/skill-router`: an MCP tool that returns a validated tool allowlist, required validation steps, and expected outputs for a caller-selected CAD-generation skill family (`solidworks-native` / `text-to-cad` / `mesh-concept`), with stub routes for branches that have no backing implementation yet.

### Modified Capabilities
(none — this change adds a new capability; it does not modify any existing tool's contract)

## Impact

- New file: `src/solidworks_mcp/tools/skill_router.py`.
- New MCP tool registered in `src/solidworks_mcp/tools/__init__.py`'s `register_tools`.
- **Does not touch COM/adapter code.** No changes to `pywin32_adapter.py`, the base adapter interface, or `mock_adapter.py` — `skill_router.py` only introspects the `SolidWorksAdapter` *class* (its public method names), never touches a live adapter instance.
- **No LLM/API dependency** — this capability makes zero outbound model calls. The classification judgment belongs entirely to whatever model is already driving the MCP session.
- No breaking changes to any existing tool or adapter contract. `text-to-cad` and `mesh-concept` branches are additive stubs in this change; #43 fills in `text-to-cad` for real afterward using this change's contract rather than redefining it.
