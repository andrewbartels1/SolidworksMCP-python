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
      include_suppressed, depth_remaining)`: call `GetComponents(True)`,
      resolve each `IComponent2`'s underlying document, flag it via
      `sw_type_info.flag_doc`, and run the existing feature traversal
      against it with its own `seen` dedupe set.
- [x] 2.3 Tag every component-derived feature descriptor with
      `component`/`component_path` (via
      `_DocumentRoutingService.document_identity`); tag the assembly's own
      features with `component: None`, `component_path: None`.
- [x] 2.4 Recurse into sub-assembly components while
      `depth_remaining > 0`; at the depth limit, emit one descriptor for
      the sub-assembly component (name + path, no nested features)
      instead of recursing.
- [x] 2.5 Handle unresolvable components (suppressed, lightweight,
      missing file) by emitting one `type: "UnresolvedComponent"`
      descriptor instead of raising or dropping the component silently.
- [ ] 2.6 Verify the `GetModelDoc2` accessor and `GetComponents` signature
      against a live SolidWorks session (`dev-test-full`, Windows +
      SolidWorks installed) — flagged as unverifiable in this environment
      per design.md's Risks section. Adjust the accessor pattern if the
      live session disagrees with the assumed member name/shape.
      **Not done — no SolidWorks available in this environment.**

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
      existing coverage gate. **1898 passed, 0 failed, 40 skipped, 73
      solidworks_only deselected; coverage 99.98%. ruff clean on all
      changed files (one pre-existing, unrelated UP046 in base.py).**
- [ ] 6.2 Update `docs/agents/com-api-pitfalls.md` if task 2.6 finds the
      live `GetModelDoc2`/`GetComponents` behavior differs from what was
      assumed during implementation. **Blocked on 2.6.**
