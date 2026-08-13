## Why

`list_features` only reads the top-level document's feature manager. Called on
an `.SLDASM`, it returns assembly-level features only — planes, origin, mates,
assembly sketches — and is blind to every sub-component's feature tree. For a
tool whose entire value is letting an LLM agent understand and reason about a
SolidWorks document, this makes the single most common real-world document
type (an assembly of parts) effectively unreadable. Closes GitHub issue #21.

## What Changes

- `list_features` detects document type. For a Part (`.SLDPRT`), behavior is
  byte-for-byte unchanged.
- For an Assembly (`.SLDASM`), it additionally:
  - Enumerates top-level component instances via `IAssemblyDoc.GetComponents`.
  - For each component, resolves its underlying `IModelDoc2` (part or
    sub-assembly) and runs the existing feature-tree traversal against it.
  - Recurses into sub-assemblies up to a configurable depth (default 2, via
    a new optional `max_assembly_depth` parameter).
  - Returns every feature — the assembly's own plus every resolved
    component's — **as a single flat list**, matching the existing return
    shape. Each feature dict gains two new optional keys, `component` and
    `component_path`, identifying which component (if any) it came from.
    An assembly's own features keep `component: None`, exactly like a
    Part's features do today.
  - A component whose underlying document cannot be resolved (suppressed,
    lightweight-and-unloaded, missing file) is represented by one synthetic
    marker row rather than silently dropped or raising.
- `include_suppressed` continues to work, now applied independently to the
  assembly's own features and to each component's features.
- Adds a mock-adapter assembly fixture so the new branch is covered without
  SolidWorks installed.

**Deliberately not the nested `{components, assembly_features}` shape
sketched in GitHub issue #21.** `adapter.list_features().data` is consumed
as a flat `list[dict]` in four places today (the `list_features` MCP tool's
`count`/`features` fields, `classify_feature_tree`, `soc_pickup.py`'s
feature-tree diffing, and the UI's `model_service.py`), all typed or
`isinstance`-checked as a list. Changing the top-level shape to a dict for
assemblies would silently break every one of them. The flat-list-plus-tag
shape below achieves the same goal (component-scoped feature visibility)
without changing `AdapterResult.data`'s type. See design.md for the full
rationale and the rejected alternative.

## Capabilities

### New Capabilities

- `tools/list-features`: behavior of the `list_features` MCP tool across Part,
  Assembly, and nested-Assembly documents, including suppression handling and
  recursion depth.

### Modified Capabilities

(none — this is the first spec written for this tool; see New Capabilities)

## Impact

- `src/solidworks_mcp/adapters/pywin32_adapter.py` — extend `list_features`
  (or its underlying implementation) to branch on document type and traverse
  `GetComponents`. Touches real COM/adapter code: this uses
  `dynamic.Dispatch`-style late binding and must apply `sw_type_info`
  flagging to every intermediate `IModelDoc2`/`IAssemblyDoc` dispatch object
  it acquires, per `docs/agents/com-api-pitfalls.md` and the COM threading
  invariants in `CLAUDE.md`. All COM calls stay on the adapter's existing
  `ComExecutor` thread — no new threading is introduced.
- `src/solidworks_mcp/adapters/base.py` — abstract signature gains an
  optional `max_assembly_depth: int = 2` parameter; return type stays
  `AdapterResult[list[dict[str, Any]]]`. Each feature dict gains optional
  `component`/`component_path` keys (both `None` for Part-document
  features and for an Assembly's own top-level features).
- `src/solidworks_mcp/adapters/mock_adapter.py` — add a mock assembly
  fixture (two components, each with a small feature list) so the new branch
  has deterministic, SolidWorks-free test coverage.
- `tests/` — new unit tests for the assembly branch; existing part-level
  `list_features` tests must keep passing unmodified.
- No new external dependencies. No change to the MCP tool's public name or
  required parameters — `include_suppressed` and the tool signature are
  unchanged, only the response shape gains fields for assemblies.
- Related: unblocks issue #20 (SolidWorks-as-Code `soc_pickup`) which needs
  assembly traversal to detect which part changed inside an assembly context.
