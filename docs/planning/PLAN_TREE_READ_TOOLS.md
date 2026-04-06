# Tree-Read / Model-Inspection Tools — Gap Analysis & Plan

**Objective**: Identify and plan the missing read-only / inspection tools that allow
an LLM agent to query the current state of an open SolidWorks document before
issuing write operations. Without these, an agent must operate blindly.

---

## Problem Statement

The current 103-tool catalog is heavily write-biased: it can *create* parts, sketches,
features, drawings, and assemblies, but it cannot *read* the current model state.
This prevents self-correcting agent loops such as:

> "What features are already in this part?" → plan next feature  
> "What components are in this assembly?" → avoid duplicate inserts  
> "What configurations exist?" → choose the right one before modifying dimensions  
> "Is there an active sketch?" → avoid creating a nested sketch by accident  

---

## Current Coverage Audit

### Adapter-level inspection methods (pywin32_adapter.py)

| Method | Exists in adapter | Exposed as MCP tool | In base.py (abstract) | In mock_adapter.py |
|--------|:-----------------:|:-------------------:|:----------------------:|:----------------:|
| `get_model_info()` | ✅ (line 1614) | ❌ | ❌ | ❌ |
| `get_mass_properties()` | ✅ | ✅ `get_mass_properties` | ✅ | ✅ |
| `get_dimension(name)` | ✅ | ✅ `get_dimension` | ✅ | ✅ |
| `get_material_properties()` | ✅ (via tool) | ✅ `get_material_properties` | — | — |
| `get_file_properties()` | ✅ (via tool) | ✅ `get_file_properties` | — | — |

### Completely absent (not in adapter OR tools)

| Needed tool | SolidWorks COM API | Return data |
|-------------|-------------------|-------------|
| `get_model_info` | `IModelDoc2::GetTitle`, `.GetType`, `.GetPathName`, `FeatureManager.GetFeatureCount` | title, path, doc type, config name, is_dirty, feature count |
| `list_features` | `FeatureManager.GetFeatureCount` + `FeatureByPositionReverse` loop | array of {name, type, suppressed} |
| `list_sketches` | Feature loop filtered by `GetTypeName2() == "ProfileFeature"` | array of sketch names |
| `list_configurations` | `IModelDoc2::GetConfigurationCount` + `GetConfigurationNames` | array of config name strings |
| `list_components` | `IAssemblyDoc::GetComponents(True)` | array of {name, path, suppressed} |
| `list_mates` | `IAssemblyDoc::GetComponents` → `GetMates` | array of mate type + entity names |
| `get_active_sketch` | `IModelDoc2::SketchManager.ActiveSketch` | sketch name or null |
| `get_sketch_entities` | `ISketch::GetSketchSegments` | array of {type, start, end} for each segment |
| `list_dimensions` | Equations manager / feature loop | array of {name, value, unit} |
| `get_active_configuration` | `IModelDoc2::GetActiveConfiguration().GetName()` | config name string |

---

## Prioritization

### Priority 1 — "What am I looking at?" (single-round awareness)

These are the tools an agent needs before ANY modelling session:

1. **`get_model_info`** — type, title, path, active config, is_dirty, feature count.
   *Partially done*: `pywin32_adapter.get_model_info()` exists but is not wired.

2. **`list_features`** — feature tree dump (name + type + suppression state).

3. **`list_configurations`** — config names so the agent can choose one before editing.

### Priority 2 — "What sketches / components exist?"

1. **`list_sketches`** — subset of feature tree filtered to sketch features.

2. **`list_components`** (assembly-only) — component paths and counts.

3. **`get_active_sketch`** — is editing mode currently inside a sketch? Which one?

### Priority 3 — "What constraints/dimensions/mates are there?"

1. **`get_sketch_entities`** — segments in the active/named sketch.

2. **`list_dimensions`** — named dimension=value pairs across the model.

3. **`list_mates`** (assembly-only) — mate relationships between components.

---

## Proposed Implementation

### Step A — Wire `get_model_info` (lowest effort, highest value)

1. Add abstract `get_model_info()` to `SolidWorksAdapter` in `adapters/base.py`
2. Add mock implementation to `adapters/mock_adapter.py`
3. Add delegating wrappers to `adapters/circuit_breaker.py` and `adapters/connection_pool.py`
4. Add `@mcp.tool("get_model_info")` to `tools/analysis.py` (or a new `tools/inspection.py`)
5. Add smoke payload to `tests/test_all_endpoints_harness.py`
6. Update tool count 103 → 104 in docs + SVG

### Step B — `list_features` (medium effort)

```python
# pywin32_adapter implementation sketch
async def list_features(self, include_suppressed: bool = False) -> AdapterResult[list[dict]]:
    def _list():
        fm = self.currentModel.FeatureManager
        count = fm.GetFeatureCount(True)
        features = []
        for i in range(count):
            feat = fm.FeatureByPositionReverse(i)
            if feat is None:
                continue
            suppressed = feat.IsSuppressed2(0, None)[0]
            if not include_suppressed and suppressed:
                continue
            features.append({
                "name": feat.Name,
                "type": feat.GetTypeName2(),
                "suppressed": suppressed,
                "position": i,
            })
        return features
    return self._handle_com_operation("list_features", _list)
```

### Step C — `list_configurations`

```python
async def list_configurations(self) -> AdapterResult[list[str]]:
    def _list():
        names = self.currentModel.GetConfigurationNames()
        return list(names) if names else []
    return self._handle_com_operation("list_configurations", _list)
```

### Step D — `list_components` (assembly only)

```python
async def list_components(self, top_level_only: bool = True) -> AdapterResult[list[dict]]:
    def _list():
        components = self.currentModel.GetComponents(top_level_only)
        if not components:
            return []
        return [
            {
                "name": c.Name2,
                "path": c.GetPathName(),
                "suppressed": c.IsSuppressed(),
                "visible": c.Visible,
            }
            for c in components
        ]
    return self._handle_com_operation("list_components", _list)
```

---

## Impact on Agent Workflows

Without these tools, an agent cannot implement these common correction loops:

```
# Current (blind) workflow
create_sketch(plane="Front")          # fails if a sketch is already open
create_extrusion(depth=10)            # fails if no closed profile

# With tree-read tools (self-correcting)
model_info = get_model_info()         # → doc type: "Part", feature_count: 3
active = get_active_sketch()          # → None (no open sketch)
features = list_features()            # → [{name:"Boss-Extrude1", type:"Boss"}]
create_sketch(plane="Front")          # now safe
```

---

## Acceptance Criteria

When implemented, each tool must:

- Pass Level A (schema validation) in `test_all_endpoints_harness.py`
- Pass Level B (smoke call against mock adapter) returning expected mock data
- Be listed in the tool catalog under an appropriate `docs/user-guide/tool-catalog/` page
- Have a mock implementation that returns realistic-looking data for CI tests
- Not require a real SolidWorks session for unit tests

---

## Related Documents

- [Tool Catalog Overview](../user-guide/tools-overview.md)
- [Integration Testing](../user-guide/integration-testing.md)
- [Real-Tool Validation Matrix](../user-guide/real-tool-validation-matrix.md)
- [Architecture](../user-guide/architecture.md)
