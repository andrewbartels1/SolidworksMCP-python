## Context

See `proposal.md` — Why, and its Revision note. This design.md describes the *current* implementation: a plain MCP tool with no LLM dependency, replacing the original dashboard-integrated design after `src/solidworks_mcp/ui/` was deleted from the repo entirely.

The COM/VBA-level routing this capability sits above (`IntelligentRouter`, `ComplexityAnalyzer` in `src/solidworks_mcp/adapters/`) is unaffected and unreferenced by this change.

Tools live in `src/solidworks_mcp/tools/`, one module per functional area (`modeling.py`, `sketching.py`, `analysis.py`, etc.), each exposing an `async def register_<area>_tools(mcp: FastMCP, adapter: SolidWorksAdapter, config: dict) -> int` function called from `src/solidworks_mcp/tools/__init__.py`'s `register_tools`. `skill_router.py` follows this exact pattern.

## Goals / Non-Goals

**Goals:**

- A single MCP tool, callable by any MCP client, that returns a validated `allowed_tools`/`validation_steps`/`expected_outputs`/`fallback` contract for a caller-selected skill family.
- `allowed_tools` is checked against the real, live `SolidWorksAdapter` interface, not a hardcoded or generated list.
- `text-to-cad` and `mesh-concept` are representable and safely stubbed before their execution branches exist.
- Zero outbound LLM/API calls from this capability.

**Non-Goals:**

- Implementing `text-to-cad` or `mesh-concept` execution logic (stubs only; #43 implements `text-to-cad` for real).
- Classifying intent on this capability's own behalf — the calling model supplies `family` as an argument; this tool does not guess it.
- Changing `IntelligentRouter`/`ComplexityAnalyzer` or any COM/adapter code.
- A UI surface for route results (moot — there is no UI in this repo anymore).
- Persisting route history/analytics.

## Decisions

**1. Module location: `src/solidworks_mcp/tools/skill_router.py`, a plain MCP tool module.**
Originally placed in `src/solidworks_mcp/ui/services/` on the theory that it was "an internal step of the existing clarify/inspect/go pipeline," not itself a `@mcp.tool()`-registered, externally-callable tool. That pipeline (and the whole `ui/` module it lived in) no longer exists. This capability's entire reason to exist now is to *be* directly callable — by Claude Code, Claude Desktop, or any other MCP client — so it belongs with every other tool module, registered the same way.

**2. No classification logic in this capability — the caller supplies `family` directly.**
The dashboard-era design had this capability call an LLM (reusing `llm_service.py`'s pydantic-ai infrastructure) to classify free-text `user_goal` into a family, with its own confidence threshold and low-confidence fallback. That's gone. The tool's input schema (`SkillRouteInput.family`) is a `Literal["solidworks-native", "text-to-cad", "mesh-concept"]` with a detailed parameter description covering what each branch means — the calling model reads that description, decides which family fits (the same kind of judgment call every other tool-selection decision already requires it to make), and passes its decision as the argument. This eliminates: a second API call and its cost/latency, a confidence-threshold tuning question, and a whole failure-mode branch (LLM call itself failing) that the old design needed a fallback shape for.

**3. Capability-catalog source: the `SolidWorksAdapter` interface (`src/solidworks_mcp/adapters/base.py`), not the MCP tool catalog.**
Unchanged from the original design, and now more clearly correct: `skill_router.py` is *itself* one of the registered MCP tools, in the same process as every other tool, with no separate dashboard/FastAPI process to reason about. Querying the live MCP tool catalog from inside a tool implementation (asking the same `FastMCP` instance this tool is registered on to introspect itself, mid-call) is unnecessary complexity for no real benefit — the `SolidWorksAdapter` class is directly importable, requires no running process, no network call, and no risk of the catalog not being ready yet.

Validation is `hasattr`-style introspection against the class directly (see `_adapter_capability_names()` / `filter_to_adapter_capabilities()` in `skill_router.py`): every public (non-underscore-prefixed), callable attribute declared on `SolidWorksAdapter`.

Trade-off accepted: this validates that a name is a *real adapter capability*, not that a corresponding `@mcp.tool()` wrapper with that exact name exists for it (the two track each other by convention, not by enforcement, across this whole codebase). Flagged as an open question below rather than built for speculatively.

**4. `solidworks-native` branch's `allowed_tools`: the full currently-declared `SolidWorksAdapter` capability set, not a curated subset.**
Only the `text-to-cad` and `mesh-concept` branches get a restrictive, explicitly-empty allowlist (until #43 lands and populates a real one). `solidworks-native` requests already legitimately span the whole existing tool surface today with no router in front of them, so this capability should not silently narrow that.

**5. Stub representation: an ordinary success response with `allowed_tools: []` and a `fallback` string, not a tool error.**
`get_skill_route("text-to-cad")` before #43 lands is not a *failure* of the routing tool — the lookup succeeded; the answer is "not executable yet, here's why." Returning `status: "error"` would conflate "this tool call went wrong" with "the requested branch doesn't exist yet," which are different things a caller needs to handle differently.

## Risks / Trade-offs

- [Risk] `allowed_tools` validated against adapter capability names could drift from what's actually exposed as an MCP tool (the two are convention-linked, not enforced) → [Mitigation] out of scope for this change per Decision 3's accepted trade-off; if a caller needs MCP-tool-level guarantees specifically, that's new scope, not a defect in this change.
- [Risk] The calling model misjudges which family fits (no confidence check inside this capability anymore) → [Mitigation] this is now an ordinary tool-selection judgment call like any other the model already makes constantly in an agentic session; the parameter description is written to make the three branches unambiguous, and a wrong pick still only ever grants tools that are real (never invented capabilities), bounding the damage.
- [Risk] `text-to-cad` stub shape must still fit #43's real implementation later, or #43 needs a follow-up change to this router → [Mitigation] the stub shape (empty `allowed_tools` + `fallback` message) is generic enough that #43 only needs to populate real values behind the same response shape, not change it.
- [Risk] `text-to-cad`'s real backing implementation (per issue #43) is the `earthtojake/text-to-cad` `cad` skill — an installable Claude Code / Codex **plugin**, not a Python dependency of this repo. A Claude Code caller can install it and get a working `text-to-cad` branch; an OpenAI/ChatGPT caller calling `get_skill_route(family="text-to-cad")` through MCP has no equivalent one-step install path today, since ChatGPT has no plugin-skill runtime analogous to Claude Code's. → [Mitigation] `get_skill_route` itself stays client-agnostic (any MCP client reads the same tool schema); the asymmetry is confined to whether a *generation* skill happens to be installed on the caller's side, which this capability correctly has no opinion about. #43 should state this plainly rather than assume Claude Code everywhere - an OpenAI caller can still populate the branch manually (run build123d generation itself, then call the handoff tool #43 adds), just without the one-command install story.

## Cross-client reach (not previously stated)

`get_skill_route`'s classification guidance lives entirely in `SkillRouteInput.family`'s parameter description (Decision 2), not in a Claude Code `SKILL.md` or any other client-specific file. This was a deliberate choice, not just a simplification: MCP tool schemas are shown to the calling model by every MCP client the same way, so this is actually *more* portable across Claude Code, Claude Desktop, and ChatGPT (via MCP) than a `SKILL.md`-based approach would have been - `SKILL.md` plugin skills are a Claude Code-specific mechanism ChatGPT has no equivalent runtime for. The `solidworks-native` and (once #43 lands) `text-to-cad` branches both work identically regardless of which model is driving the session; only the availability of the upstream `text-to-cad` *generation* skill itself varies by client, per the risk above.

## Migration Plan

Not applicable — net-new module and capability, no existing behavior replaced. Rollback is deleting `skill_router.py` and its registration line in `tools/__init__.py`; no data migration involved (this capability never persisted anything).

## Open Questions

- Whether a caller ever needs MCP-tool-level validation (does a corresponding `@mcp.tool()` wrapper exist with this exact name) rather than adapter-capability validation. Not needed for any known caller today; deferred until one exists.
