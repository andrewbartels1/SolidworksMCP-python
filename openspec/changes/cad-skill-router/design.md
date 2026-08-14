## Context

See `proposal.md` - Why. The existing clarify/inspect/go pipeline lives in `src/solidworks_mcp/ui/services/llm_service.py`: `request_clarifications` (line 509), `inspect_family` (line 645), and `run_go_orchestration` (line 854), all `async def`. `inspect_family` already performs LLM-backed classification today — but of a different, pre-existing concept: it classifies the *SolidWorks feature-tree family* of a target part (`revolve | extrude | sheet_metal | advanced_solid | assembly | drawing | unknown`, stored as `proposed_family` in session metadata), used for feature-tree reconstruction inspection sequencing. That is unrelated to, and already uses the word "family" for, a different axis of classification than this change's skill-family routing.

The COM/VBA-level routing this change sits above (`IntelligentRouter`, `ComplexityAnalyzer` in `src/solidworks_mcp/adapters/`) is unaffected and unreferenced by `ui/services/` today.

The MCP server itself is `SolidWorksMCPServer` in `src/solidworks_mcp/server.py`, which owns `self.mcp = FastMCP("SolidWorks MCP Server")` (line 88). **There is no import or reference from anything under `src/solidworks_mcp/ui/` to `server.py` or its `FastMCP` instance** — confirmed by search, zero matches.

The dashboard and the MCP server are two independent processes. `ui/prefab_dashboard.py` (a `prefab_ui` app) talks over HTTP to `SOLIDWORKS_UI_API_ORIGIN` (default `http://127.0.0.1:8766`), which is served by a *separate* FastAPI app, `src/solidworks_mcp/ui/server.py` (its own `uvicorn` process, distinct from `solidworks_mcp/server.py`'s FastMCP server). That FastAPI app's checkpoint execution path (`ui/services/checkpoint_service.py:219-220`) constructs its own SolidWorks adapter directly via `create_adapter()` from `solidworks_mcp.adapters` — it does not dispatch through MCP tool calls or `@mcp.tool()` names at all. So the process this router's caller (`llm_service.py`) actually runs in has no concept of "MCP tool catalog" in the first place; it already works in terms of adapter capabilities.

The tool catalog also has a separate, unrelated static generator (`src/utils/generate_tool_catalog.py`) that AST-parses `@mcp.tool()` decorators for documentation purposes at build time; it does not run at request time, is not a live source, and (per the finding above) isn't even the right kind of catalog for this router's actual caller.

## Goals / Non-Goals

**Goals:**
- Single async entry point, callable from `llm_service.py`, that returns a `SkillRoute` for a CAD-generation request.
- The route's `allowed_tools` is checked against the actually-running server's registered tools, not a hardcoded or file-generated list.
- `text-to-cad` and `mesh-concept` are representable and safely stubbed before their execution branches exist.
- A low-confidence request never silently commits to a branch.

**Non-Goals:**
- Implementing `text-to-cad` or `mesh-concept` execution logic (stubs only; #43 implements `text-to-cad` for real).
- Changing `IntelligentRouter`/`ComplexityAnalyzer` or any COM/adapter code.
- A UI surface for route results (#44's concern).
- Persisting route history/analytics.

## Decisions

**1. Module location: `src/solidworks_mcp/ui/services/skill_router.py`.**
Co-located with `llm_service.py`, the module that calls it, rather than `tools/automation.py`. Alternative considered: `tools/automation.py` (the integration report's literal wording, "beside... in the automation layer") — rejected because this router classifies intent *before* dispatch as an internal step of the existing clarify/inspect/go pipeline; it is not itself a `@mcp.tool()`-registered, externally-callable tool, so it belongs with the orchestration code that calls it, not the tool-registration module.

**2. Function name: `classify_generation_route`, not `classify_skill_family`.**
The proposal and issue #42 both used "family" for the new concept, but `inspect_family`/`proposed_family` in this same file already mean something else (SolidWorks feature-tree family). Reusing "family" for skill-routing risks a reader confusing the two, especially since both are LLM-classification steps in the same pipeline. Decision: name the new function `classify_generation_route`; the returned `SkillRoute.family` field keeps `family` only as an attribute name (lower collision risk at that granularity, and matches the spec's plain-language "skill family" wording), not as the function's own name. This does not affect the delta spec, which describes behavior, not identifiers.

**3. Capability-catalog source: the `SolidWorksAdapter` interface (`src/solidworks_mcp/adapters/base.py`), not the MCP tool catalog.**
Revised during the design review checkpoint after tracing the actual process topology (see Context above): `llm_service.py`'s process doesn't talk MCP at all — its sibling code in `checkpoint_service.py` already validates and dispatches purely in terms of adapter capabilities via `create_adapter()`. Chasing an MCP `list_tools()` call from this process would mean either standing up a real MCP client connection to a separate, possibly-not-running `solidworks-mcp` process (invasive, and a new failure mode: what happens when that process isn't up?), or somehow sharing an in-process `FastMCP` instance that doesn't exist in this process to begin with (Context confirms zero references).

Decision: rename `allowed_tools` conceptually to mean **adapter capability names** — the public async methods declared on `SolidWorksAdapter` (`base.py:307` onward, e.g. `list_features`, `create_extrusion`, `get_mass_properties`). Validation is `hasattr(SolidWorksAdapter, name) and not name.startswith("_")` (or an equivalent introspection helper) against the class directly — a plain Python import, no running process, no network call, no new plumbing. This is strictly simpler than the original MCP-catalog approach and removes the cross-process risk entirely, since `base.py` is importable from whichever process ends up calling `classify_generation_route`.

Trade-off accepted: this validates that a name is a *real adapter capability*, not that a corresponding `@mcp.tool()` wrapper exists for it (the two currently track each other closely by convention, but nothing enforces it). If `solidworks-native` routing ever needs to guarantee MCP-tool-level availability specifically (e.g. for a Claude Code client calling through MCP rather than the dashboard), that's a distinct, currently-hypothetical caller this change does not need to support yet — flag as an open question below rather than build for it speculatively.

**4. Classification backend: LLM-driven, reusing `llm_service.py`'s existing model-call infrastructure (same provider/config plumbing `inspect_family` already uses), not a keyword/regex heuristic.**
Alternative considered: a keyword/rules engine (e.g., "assembly" or "edit" → solidworks-native) — rejected as brittle, and it would duplicate judgment `inspect_family`/`request_clarifications` already apply to similar free-text goals.

**5. `solidworks_native` branch's `allowed_tools`: the full currently-registered SolidWorks-native tool surface (i.e., every live tool not reserved for `text-to-cad`/`mesh-concept`), not a curated subset.**
Only the `text-to-cad` and `mesh-concept` branches get a restrictive, explicitly-named allowlist (per proposal: `{import_generated_step, get_model_info, list_features, ...}` once #43 lands). `solidworks-native` requests already legitimately span the whole existing tool surface today with no router in front of them, so this change should not silently narrow that.

**6. Stub representation: an ordinary `SkillRoute` with `allowed_tools: []` and `fallback` set to an explicit "branch not yet available" message, not an exception.**
Matches the delta spec's stub scenarios, which expect a returned route. Alternative considered: raise `NotImplementedError` — rejected, forces every caller to add exception handling for what is really just a valid, low/no-capability route.

**7. Failure mode when the underlying LLM classification call itself errors (timeout, provider error):** return a `SkillRoute` with `confidence: 0.0` and `fallback` describing the failure, reusing the same shape as the low-confidence and stub cases rather than a distinct error type. This keeps callers handling one shape (`SkillRoute`) instead of a route-or-exception union.

## Risks / Trade-offs

- [Risk] LLM misclassifies intent (e.g. treats an assembly edit as `text-to-cad`) → [Mitigation] confidence threshold + mandatory `fallback` (spec requirement); low-confidence routes surface to the orchestrator instead of silently executing.
- [Risk] `allowed_tools` validated against adapter capability names could drift from what's actually exposed as an MCP tool (the two are convention-linked, not enforced) → [Mitigation] out of scope for this change per Decision 3's accepted trade-off; if a caller needs MCP-tool-level guarantees specifically, that's new scope, not a defect in this change.
- [Risk] Tool catalog can change between classification and actual dispatch (e.g. a tool is removed mid-session) → [Mitigation] out of scope for this change; dispatch already goes through the real MCP/tool-call path, which fails on its own if a tool is truly gone. This change only guarantees the *route* doesn't claim a nonexistent tool at classification time.
- [Risk] `text-to-cad` stub shape must still fit #43's real implementation later, or #43 needs a follow-up change to this router → [Mitigation] the delta spec's tool-catalog and stub requirements are written generically (empty `allowed_tools` + `fallback` message) so #43 only needs to populate real values behind the existing `SkillRoute` shape, not change the shape. Reference this design doc from #43's own proposal.
- [Risk] Adding an LLM classification call to every CAD-generation request adds latency/cost → [Mitigation] reuse `llm_service.py`'s existing model-call infrastructure (no new provider/config) and keep the classification prompt small (three named branches, not open-ended reasoning).

## Migration Plan

Not applicable — net-new module and capability, no existing behavior replaced. Rollback is deleting `skill_router.py`, its call site in `llm_service.py`, and the new `FastMCP`-instance plumbing from `server.py`; no data migration involved.

## Open Questions

- Whether a future MCP-protocol caller (e.g. Claude Code calling through the `solidworks-mcp` CLI's FastMCP server directly, rather than through the dashboard's FastAPI backend) needs its own capability check against the actual MCP tool catalog rather than the adapter interface. Not needed for this change's known callers; deferred until such a caller exists.
- Exact confidence threshold for triggering `fallback` (e.g. 0.6 vs 0.7) — tunable during implementation, does not change the requirement that some threshold exists and is honored.
- Whether `validation_steps`/`expected_outputs` are free-text strings or a more structured type — free-text is sufficient for v1 (stubs and `solidworks-native`); can be tightened later without a spec change since the delta spec doesn't constrain that field's internal type.
