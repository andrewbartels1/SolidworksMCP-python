## Why

A modelling tool that returns `status: "success"` does not prove the model is
right: SolidWorks accepts some calls and silently does nothing (COM pitfalls
#19 and #23 are both "success, but 0 mm³ removed"). An agent today has to
stitch four read tools together, and still cannot read a bounding box, a
solid-body count or a mate count at all. Issue #173 asks for one call that
reads the model back and returns a pass/fail verdict against what the agent
expected; the bracket demo (#147) needs it as its final step.

## What Changes

- **New tool `verify_model`.** It reads the active part or assembly back and
  checks it against optional expectations: mass and volume within a relative
  tolerance, bounding-box size within an absolute tolerance, modelling-feature
  count and solid-body count; for assemblies also component count, mate count
  and "no interference". Every check reports expected, actual, tolerance and
  `passed` (`true`, `false`, or `null` when it can't be measured). There is
  also one overall verdict: `pass`, `fail`, `inconclusive`, or `report_only`
  when no expectations were given. Called with no expectations, it is a
  one-call read-back report.
- **New adapter read `get_model_geometry_summary`:** bounding box, solid-body
  count, volume, and for assemblies component and mate counts. It never forces
  a rebuild, so it cannot clear the live selection the way
  `get_mass_properties` does (pitfall #23). Added to the base interface, the
  pywin32 adapter, the mock adapter, and the circuit-breaker and
  connection-pool wrappers.
- **Measured change on three modelling tools (issue #173 addendum).**
  `create_extrusion`, `create_revolve` and `create_cut_extrude` add a
  `measured_change` block to their success reply: volume and bounding box
  before and after, plus the deltas. It is best-effort and never fails or
  slows the tool beyond the two reads.
- The mock adapter tracks mates added through `add_mate`, so mate counts are
  testable without SolidWorks.
- No breaking changes. Existing tools keep their payloads; the three modelling
  tools only gain a key.

**Touches COM/adapter code.** The change adds a new COM read path in the
pywin32 adapter (bounding box via body extreme points and the assembly box,
`GetBodies2`, mate-group traversal) and new methods on `base.py`,
`mock_adapter.py` and both wrappers. That carries the usual COM-threading and
late-binding risk from CLAUDE.md:
- route everything through `_handle_com_operation`;
- flag every interface;
- no new threads.

## Capabilities

### New Capabilities
- `tools/model-verification`: the `verify_model` tool. It covers its inputs,
  its checks and their tolerances, the per-check result and overall verdict,
  "not determinable" handling, and the errors.
- `tools/model-geometry-summary`: the adapter read that reports bounding box,
  body count, volume, component count and mate count without side effects on
  the model or selection.
- `tools/measured-feature-change`: the `measured_change` block that extrude,
  revolve and cut-extrude add to their success replies.

### Modified Capabilities
None. `openspec/specs/` has no main specs yet, and existing tool behaviour is
unchanged apart from the additive reply key described above.

## Impact

- **Adapters:**
  - `base.py`: new `get_model_geometry_summary`, which errors by default.
  - `solidworks/io.py`: the real implementation (pywin32 mixin).
  - `mock_adapter.py`: the summary, plus mate tracking in `add_mate`.
  - `circuit_breaker.py` and `connection_pool.py`: forwarding.
- **Tools:**
  - `analysis.py`: the new `verify_model`.
  - `modeling.py`: extrude, revolve and cut-extrude replies.
- **Tool count:** 151 → 152. Update the docs and server counts via
  `check_tool_docs_consistency.py --fix`, the tool reference page and the
  CHANGELOG.
- **Tests:**
  - `tests/solidworks_mcp/tools/test_analysis_verify_model.py`
  - `tests/solidworks_mcp/tools/test_modeling_measured_change.py`
  - mock adapter and wrapper tests beside their modules
  - a live test under `tests/live/`, run only with the maintainer's go-ahead
    at `SW_TEST_PACE_SECONDS=4`
- **No new dependencies.**
