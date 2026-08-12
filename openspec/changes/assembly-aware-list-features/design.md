## Context

`list_features` today is `_FeatureSelectionService.list_features` in
`pywin32_adapter.py` (mirrored by `mock_adapter.py`, wrapped by
`circuit_breaker.py` and `connection_pool.py`, exposed via the async
`SolidWorksSelectionMixin.list_features` in `adapters/solidworks/selection.py`).
It walks `currentModel.FirstFeature()` / `GetNextFeature()` plus a
`FeatureByPositionReverse` fallback pass against a single document's feature
manager. It never inspects document type and never looks at assembly
components — see proposal.md for why that's a problem.

`adapter.list_features().data` is consumed as a flat `list[dict]` in four
places already: the `list_features` MCP tool (`count = len(result.data)`,
`"features": result.data or []`), `classify_feature_tree`
(`classify_feature_tree_snapshot(model_info, features)`), `soc_pickup.py`'s
`_new_features` diffing (compares entries by `name`), and the UI's
`model_service.py` (`isinstance(feature_result.data, list)`). None of these
are optional call sites to migrate later — they're existing, in-use
behavior (SoC pickup diffing and the UI feature panel).

The codebase already has the pieces this needs: `sw_type_info.flag_doc(obj,
doc_type)` for method-flagging a newly-acquired document dispatch,
`DOC_TYPE_TO_INTERFACES` mapping `GetType()`'s 1/2/3 to Part/Assembly/
Drawing, and `_DocumentRoutingService.document_identity(document)` for
robust path/title extraction that already handles COM objects exposing
`GetPathName`/`GetTitle` as either methods or properties.

## Goals / Non-Goals

**Goals:**
- Assemblies return every component's features, not just the assembly's
  own planes/origin/mates.
- Zero behavior change for Part documents.
- Zero behavior change for the four existing consumers of
  `list_features().data` unless they choose to read the new
  `component`/`component_path` keys.

**Non-Goals:**
- Matching issue #21's literal `{type, components, assembly_features}`
  JSON sketch. That shape is superseded by the flat-list-plus-tag design
  below (see Decisions) — the issue's acceptance criteria are satisfied in
  spirit (per-component feature visibility, `include_suppressed` at both
  levels, bounded recursion) but not in literal response shape.
- Assembly mate enumeration, BOM data, or configuration-specific feature
  suppression — out of scope, tracked separately under issue #23's phased
  tool-surface proposal.
- Changing `list_features`'s required parameters. `include_suppressed`
  keeps its meaning and position; `max_assembly_depth` is additive and
  optional.

## Decisions

### Decision: Flat list with `component`/`component_path` tags, not a nested response

**Chosen**: Keep `AdapterResult[list[dict[str, Any]]]` as the return type
for every document type. For Assembly documents, concatenate the
assembly's own features with every resolved component's features into one
list. Each descriptor gets two new optional keys: `component` (the owning
component's name, or `None` for the document's own features) and
`component_path` (that component's resolved document path, or `None`).

**Rejected alternative**: Return a structured object
(`{"type": ..., "components": [...], "assembly_features": [...]}`) as
issue #21 sketches. Rejected because `AdapterResult.data`'s type would
then depend on document type (list for Parts, dict for Assemblies), and
four existing call sites assume `list[dict]` unconditionally:
`len(result.data)` in the MCP tool, `classify_feature_tree_snapshot`,
`soc_pickup.py`'s name-based feature diffing, and `model_service.py`'s
`isinstance(..., list)` guard. Shipping the nested shape would silently
degrade SoC pickup diffing and the UI's feature panel for every assembly
— a regression, not just an inconvenience for future callers.

**Rejected alternative**: A new sibling adapter method (e.g.
`list_assembly_components`) that leaves `list_features` untouched.
Rejected because it doesn't address the actual complaint in issue #21 —
`list_features` itself stays blind to assembly contents — and it would
give agents two tools to call and reconcile instead of one, working
against the "read-before-write" workflow `list_features` exists for.

### Decision: Component traversal lives in `_FeatureSelectionService`, doc-type branch first

`_FeatureSelectionService.list_features` (sync, runs inside
`_handle_com_operation` on the adapter's COM executor thread — no new
threading) gets a document-type check up front via
`currentModel.GetType()` against the existing `swDocASSEMBLY` constant.
Part and Drawing documents fall through to exactly the current code path
unchanged. Assembly documents additionally call a new private helper,
`_list_assembly_component_features(assembly_doc, include_suppressed,
depth_remaining)`, which:
1. Calls `assembly_doc.GetComponents(True)` (top-level only) to get
   `IComponent2` instances.
2. For each, resolves the underlying document (trying `GetModelDoc2`,
   consistent with this codebase's existing `_get_attr_or_call` fallback
   pattern for COM members that may bind as method or property — the
   exact accessor needs confirming against a live SolidWorks session per
   `docs/agents/com-api-pitfalls.md`; flagged as a risk below).
3. Applies `sw_type_info.flag_doc(resolved_doc, resolved_doc.GetType())`
   before touching it, per the COM threading/late-binding invariants in
   CLAUDE.md.
4. Reuses the existing `list_features`/`_append_feature_to` traversal
   against the resolved document, then tags every resulting descriptor
   with `component`/`component_path` via `_DocumentRoutingService
   .document_identity`.
5. If `resolved_doc.GetType()` is itself Assembly and `depth_remaining >
   0`, recurses with `depth_remaining - 1`; at `depth_remaining == 0`,
   emits one descriptor for the sub-assembly component itself (name +
   path, no nested features) instead of recursing further.
6. If the component can't be resolved at all, emits one synthetic
   descriptor (`type: "UnresolvedComponent"`) instead of raising.

### Decision: `max_assembly_depth` is a new optional parameter, default 2

Threaded through the abstract method (`base.py`), both adapters
(`pywin32_adapter.py`, `mock_adapter.py`), the wrapping layers
(`circuit_breaker.py`, `connection_pool.py`), and optionally exposed on
`ListFeaturesInput` (currently only `include_suppressed`) for MCP callers
who want to override it. Default of 2 matches the issue's ask and covers
the common one-level-of-sub-assembly case without unbounded recursion risk
on deeply nested assemblies.

## Risks / Trade-offs

- [Risk] The exact COM accessor for "get an `IComponent2`'s underlying
  document" (`GetModelDoc2` vs. a differently-cased or differently-shaped
  member under late binding) can't be verified without a live SolidWorks
  session — this environment has none. → Mitigation: implement using the
  same `_get_attr_or_call`/`_attempt` defensive pattern already used
  throughout `pywin32_adapter.py` for COM members with binding ambiguity,
  add a mock-adapter fixture that exercises the intended shape, and flag
  this explicitly for verification on `dev-test-full` (real SolidWorks)
  before merge, per CLAUDE.md's testing guidance.
- [Risk] Deeply nested or very large assemblies could make `list_features`
  slow (resolving and traversing many component documents). →
  Mitigation: `max_assembly_depth` default of 2 bounds recursion; this is
  a read-only, no-rebuild operation so no COM rebuild cost is added.
- [Risk] Two components could legitimately share a `name`/`type` pair
  (e.g. two instances of the same part), which would collide with the
  existing per-document `(name, type)` dedupe-`seen` set if that set were
  reused across components. → Mitigation: the dedupe set is scoped per
  resolved document (as it is today, per document), not shared across
  the whole assembly traversal — each component's traversal gets its own
  `seen` set.
- [Trade-off] `component`/`component_path` being `None` for both "this is
  the document's own feature" and "no component information available"
  is slightly ambiguous, but matches the simplest interpretation
  consumers will already apply (`if feature.get("component"): ...`) and
  avoids adding a third state.

## Open Questions

None — the shape decision above was the one open question that would
have changed the spec or task breakdown, and it's resolved.
