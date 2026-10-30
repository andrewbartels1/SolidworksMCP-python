## 1. Adapter interface

- [x] 1.1 Add optional `max_assembly_depth: int = 2` parameter to the
      abstract `list_features` in `src/solidworks_mcp/adapters/base.py`;
      document the new `component`/`component_path` keys on the returned
      feature descriptors in the docstring.
- [x] 1.2 Thread `max_assembly_depth` through `circuit_breaker.py` and
      `connection_pool.py` wrapper methods.

## 2. Real adapter: assembly traversal

- [x] 2.1 In `_FeatureSelectionService` (`pywin32_adapter.py`), branch on
      `currentModel.GetType()` (existing `swDocASSEMBLY` constant) at the
      top of `list_features`; Part/Drawing path is unchanged.
- [x] 2.2 Implement `_list_assembly_component_features(assembly_doc,
      include_suppressed, depth_remaining, parent_component)`: call
      `GetComponents(True)`, resolve each `IComponent2`'s underlying
      document, flag it via `sw_type_info.flag_doc`, and run the existing
      feature traversal against it with its own `seen` dedupe set.
- [x] 2.3 Tag every component-derived feature descriptor with
      `component`/`component_path`/`component_parent` (via
      `_DocumentRoutingService.document_identity`); tag the assembly's own
      features with `component: None`, `component_path: None`,
      `component_parent: None`.
- [x] 2.4 Recurse into sub-assembly components while
      `depth_remaining > 0`; at the depth limit, emit one descriptor for
      the sub-assembly component (name + path, no nested features)
      instead of recursing.
- [x] 2.5 Handle unresolvable components (suppressed, lightweight,
      missing file) by emitting one `type: "UnresolvedComponent"`
      descriptor instead of raising or dropping the component silently.
- [x] 2.6 Verify the `GetModelDoc2` accessor and `GetComponents` signature
      against a live SolidWorks session. **Done 2026-08-11 against a real,
      running SolidWorks 2026 (build 34.3.0) instance and the built-in
      U-Joint sample assembly (`UJoint.SLDASM`, containing nested
      sub-assembly `crank sub.SLDASM`).** `GetComponents(True)` and
      `IComponent2.GetModelDoc2` are confirmed correct — but the initial
      implementation had two real, live-only bugs neither mock adapter nor
      unit tests could have caught:
      1. `document.GetType()` called with bare parens raises
         `TypeError: 'int' object is not callable` on a freshly-fetched
         `swApp.ActiveDoc` (unflagged dispatch resolves it as a property,
         not a method) — silently swallowed by `_attempt`, which made
         every Assembly look like doc_type 0 and skip the whole component
         branch. Fixed by routing through `_get_attr_or_call`.
      2. `IComponent2.GetModelDoc2` raised
         `com_error: Member not found` on every component because
         `IComponent2` was never flagged via `sw_type_info.flag_methods`
         before calling it — every component silently became
         `UnresolvedComponent`. Fixed by flagging `IComponent2` before
         resolving.
      Documented as pitfalls #11 and #12 in
      `docs/agents/com-api-pitfalls.md`. After both fixes, a live run
      resolved all 11 real components across 2 levels of nesting (8
      top-level + 3 inside the sub-assembly) with zero
      `UnresolvedComponent` rows — see
      `docs/getting-started/tutorial-parts/list_features_assembly_demo.py`.

## 3. Mock adapter

- [x] 3.1 Add an assembly fixture to `mock_adapter.py`: a mock `.SLDASM`
      with two top-level part components (each with a small feature list)
      and one nested sub-assembly component one level deep.
- [x] 3.2 Extend `mock_adapter.py`'s `list_features` to branch on the mock
      document's type the same way the real adapter does, returning the
      flattened, tagged list for the assembly fixture and honoring
      `max_assembly_depth` and `include_suppressed`.

## 4. Tool layer

- [x] 4.1 Add optional `max_assembly_depth` field (default 2) to
      `ListFeaturesInput` in `src/solidworks_mcp/tools/file_management.py`
      and pass it through to `adapter.list_features`.
- [x] 4.2 Confirm the `list_features` MCP tool handler needs no other
      changes — `result.data or []` and `len(result.data or [])` already
      work unmodified against the flattened list.

## 5. Tests

- [x] 5.1 Unit tests for the assembly branch: two-component assembly
      returns both components' features tagged correctly; assembly-level
      features carry `component: None`.
- [x] 5.2 Unit test for `include_suppressed` applied independently per
      component and at the assembly level.
- [x] 5.3 Unit test for sub-assembly recursion at depth 1 (default depth
      2) and for the depth-limit case (component appears as a single
      descriptor, not expanded, not an infinite loop).
- [x] 5.4 Unit test for an unresolvable component producing one
      `UnresolvedComponent` descriptor without failing the whole call.
- [x] 5.5 Regression test confirming existing Part-document
      `list_features` output is byte-for-byte unchanged.
- [x] 5.6 Regression test confirming `classify_feature_tree` and the
      `list_features` MCP tool's `count`/`features` fields still work
      against the flattened assembly result (guards the decision in
      design.md against silent breakage).

## 6. Verification

- [x] 6.1 Run `.\dev-commands.ps1 dev-lint` and `.\dev-commands.ps1
      dev-test`; confirm the full mock-only suite passes with the
      existing coverage gate. **1898+ passed, 0 failed, coverage ~99.9%+.
      ruff clean on all changed files (one pre-existing, unrelated UP046
      in base.py, confirmed identical on main).**
- [x] 6.2 Update `docs/agents/com-api-pitfalls.md` with the live findings
      from 2.6. **Done — items #11 and #12.**
- [x] 6.3 Run `.\dev-commands.ps1 dev-test-full` (real SolidWorks
      integration, `SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true`,
      `--cov-fail-under=99`). **1925 passed, 42 skipped, 49 failed,
      coverage 99.91% (gate passed). Every `list_features`/assembly test
      passed, including the new live-adjacent ones. The 49 failures are
      all `create_part: Failed to create new part` — confirmed
      pre-existing and unrelated: reproduces identically with this
      branch's commits `git stash`-ed (clean `aee4297`), and persists
      even after closing every open document, so it is not a
      too-many-open-docs issue either. Root cause is degraded state in
      the long-running `SLDWORKS.exe` process itself (this machine's
      instance had been through hours of automation churn across this
      session by the time `dev-test-full` ran) — out of scope for this
      change, since it never touches `create_part`/`NewPart`/template
      resolution. Flagged for the repo owner; a SolidWorks restart is
      the likely fix per CLAUDE.md's troubleshooting runbook, but
      restarting the user's live application wasn't done unprompted.**

## 7. Nested component tree (added after initial review)

The flat list-with-tags shape (see design.md's rejected-alternative
analysis) is still the adapter contract, but it doesn't by itself capture
parent/child structure between components — e.g. that `crank-arm-1` lives
*inside* `crank sub-1`, not alongside it. Addressed additively:

- [x] 7.1 Add a `component_parent` key to every feature descriptor (the
      immediate parent component's name, or `None` for a top-level
      component or a document's own feature) in both adapters.
- [x] 7.2 Add `build_component_tree(features)` to
      `src/solidworks_mcp/utils/feature_tree_classifier.py`: a pure
      function that reconstructs the real nested
      `{"features": [...], "components": {name: {"path", "features",
      "components"}}}` tree from the flat, tagged list. Adapter contract
      stays flat; this is a derived view for callers who want to look at
      structure rather than scan tags.
- [x] 7.3 Expose the tree as an additive `assembly_tree` field on the
      `list_features` MCP tool response, alongside the unchanged
      `features`/`count` fields.
- [x] 7.4 Unit tests for `build_component_tree` (empty input, Part-only,
      flat top-level siblings, nested sub-assembly, marker rows excluded
      from `features` but present as nodes).
- [x] 7.5 Re-verified live: `crank sub-1`'s three part components nest
      correctly under it in the tree, not flattened alongside its
      top-level siblings.
