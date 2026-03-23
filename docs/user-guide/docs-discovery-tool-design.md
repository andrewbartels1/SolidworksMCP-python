# SolidWorks Docs Discovery Tool Design

## Overview

The **SolidWorks Docs Discovery Tool** automatically indexes all available COM objects, methods, properties, and VBA library references for the installed SolidWorks version. This enables:

- **Intelligent context building** for LLM-guided MCP tool selection
- **Self-documenting server** that knows its own capabilities
- **Regression detection** across SolidWorks versions
- **Foundation for RAG** (Retrieval-Augmented Generation) backends

## Architecture

### Components

```
docs_discovery.py
├── SolidWorksDocsDiscovery (Core indexer)
│   ├── discover_com_objects() → dict
│   │   ├── Connect to SolidWorks COM
│   │   ├── Enumerate core objects (ISldWorks, IModelDoc2, etc.)
│   │   ├── Extract methods/properties from COM types
│   │   └── Return indexed catalog
│   │
│   ├── discover_vba_references() → dict
│   │   ├── Probe standard libraries (VBA, stdole, Office, VBIDE, SolidWorks)
│   │   ├── Check availability of each reference
│   │   └── Return reference status
│   │
│   ├── discover_all() → dict
│   │   ├── Call discover_com_objects()
│   │   ├── Call discover_vba_references()
│   │   └── Return complete index
│   │
│   ├── save_index() → Path
│   │   └── Export to solidworks_docs_index.json
│   │
│   └── create_search_summary() → dict
│       └── Return quick-reference statistics
│
├── register_docs_discovery_tools() → FastMCP tools
│   └── discover_solidworks_docs MCP tool
│
└── Integration
    ├── tools/__init__.py registers via register_tools()
    ├── Output: .generated/docs-index/solidworks_docs_index.json
    └── Test validation: tests/test_tools_docs_discovery.py
```

## Tool Specification

### `discover_solidworks_docs(output_dir?, include_vba?) → dict`

**Purpose**: Index all SolidWorks COM/VBA documentation available on the install

**Input**:

- `output_dir` (str, optional): Directory for storing index (default: .generated/docs-index)
- `include_vba` (bool): Include VBA library discovery (default: true)

**Output on Success**:

```json
{
  "status": "success",
  "message": "Discovered 15 COM objects, 847 methods, 423 properties",
  "index": {
    "version": "1.0",
    "solidworks_version": "2024",
    "com_objects": {
      "ISldWorks": {
        "methods": ["Visible", "OpenDoc6", "CloseDoc", ...],
        "properties": ["RevisionNumber", "SupportsText", ...],
        "method_count": 182,
        "property_count": 95
      },
      "IModelDoc2": {...},
      "IPartDoc": {...},
      "IAssemblyDoc": {...},
      "IDrawingDoc": {...}
    },
    "vba_references": {
      "VBA": {"description": "Visual Basic for Applications", "status": "available"},
      "stdole": {"description": "OLE Automation", "status": "available"},
      "SldWorks": {"description": "SolidWorks API", "status": "available"},
      ...
    },
    "total_methods": 847,
    "total_properties": 423
  },
  "summary": {
    "total_com_objects": 5,
    "total_methods": 847,
    "total_properties": 423,
    "solidworks_version": "2024",
    "available_vba_libs": ["VBA", "stdole", "Office", "SldWorks", ...]
  },
  "output_file": ".generated/docs-index/solidworks_docs_index.json",
  "execution_time": 2.341
}
```

**Output on Error**:

```json
{
  "status": "error",
  "message": "SolidWorks not running; cannot index COM"
}
```

## Operational Modes

### 1. Direct Execution (Windows PowerShell)

**Command**:

```powershell
.\dev-commands.ps1 -Command dev-docs-discovery
```

**Behavior**:

- Checks if SolidWorks is running
- Executes indexing via Python embedded in PowerShell
- Displays summary statistics
- Saves JSON index to `.generated/docs-index/solidworks_docs_index.json`

**Requirements**:

- Windows 11 (PowerShell 7+)
- SolidWorks running
- `win32com` library available in environment
- Micromamba Python environment with `solidworks_mcp` package

### 2. MCP Tool Invocation

```python
# From any MCP client
result = await mcp_client.call_tool(
    "discover_solidworks_docs",
    {
        "output_dir": "my_docs_index",
        "include_vba": true
    }
)
```

### 3. Python Module Usage

```python
from solidworks_mcp.tools.docs_discovery import SolidWorksDocsDiscovery

discovery = SolidWorksDocsDiscovery(output_dir="indexes")
index = discovery.discover_all()
discovery.save_index()
summary = discovery.create_search_summary()
print(f"Discovered {summary['total_methods']} methods")
```

## Output Artifacts

### Primary Artifact: `solidworks_docs_index.json`

**Location**: `.generated/docs-index/solidworks_docs_index.json`

**Content**:

- Complete COM object enumeration
- Method/property catalogs per object
- VBA library availability matrix
- SolidWorks version metadata

**Size**: ~150-300 KB (depends on SolidWorks version and installed add-ins)

**Usage**:

- Input for RAG backends
- Regression detection across version upgrades
- Context enrichment for LLM prompting
- Documentation fallback when COM queries fail

## Deterministic Testing

### Test Suite: `tests/test_tools_docs_discovery.py`

**Windows-only Tests** (require SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true):

1. **`test_discover_solidworks_docs_available`**
   - Verifies tool is registered in MCP server
   - Fails gracefully if tool not yet integrated

2. **`test_discover_solidworks_docs_execution`**
   - Executes real indexing against live SolidWorks
   - Validates output structure and data integrity
   - Checks file artifact creation
   - Allows for known COM errors (e.g., SolidWorks not running)

3. **`test_docs_discovery_import`**
   - Verifies module imports successfully
   - Checks required methods exist
   - Non-real-integration; always runs on Windows

4. **`test_docs_discovery_output_dir_creation`**
   - Validates output directory auto-creation
   - Non-real-integration; always runs on Windows

**Run Commands**:

```bash
# Fast test (import + directory creation)
python -m pytest tests/test_tools_docs_discovery.py -m "not solidworks_only"

# Full test (with real SolidWorks)
SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true python -m pytest tests/test_tools_docs_discovery.py
```

## Known Limitations

### Current Implementation (v1.0)

1. **Windows-Only**: Requires `win32com` and COM access (not available on WSL, Linux, macOS)
2. **COM Type Limitation**: Extracts only top-level COM interfaces; nested object trees not fully indexed
3. **VBA Library Probing**: Tests standard libraries; custom add-in libraries may not be detected
4. **No RAG Backend**: Generates JSON; does NOT include vector embedding or SQLite indexing
5. **No Real-Time Updates**: Index is static; requires manual re-run when SolidWorks version changes

### Future Enhancements

- [ ] Cross-platform support via mock adapter
- [ ] Deep COM tree traversal for nested objects
- [ ] Automatic vector embedding for RAG (sqlite-vec, LangChain integration)
- [ ] Watch mode for SolidWorks version changes
- [ ] Incremental indexing (only update changed objects)
- [ ] Custom add-in library detection
- [ ] Semantic search interface for documentation queries

## Integration with Other Components

### File Management Convenience Tools

The new lifecycle tools (load_part, save_part, load_assembly, save_assembly) can reference the docs discovery index to:

- Automatically provide context about file types supported
- Recommend workflow patterns based on available COM methods
- Hint at alternative operations if a method is unavailable

### Backlog Linking

From SWChecklist.md:

```markdown
[ ] Add a local docs-query tool that reads installed SolidWorks API help and VBA references directly for the active version
[ ] Evaluate optional RAG backend for docs discovery (sqlite-vec, LangChain, or equivalent local vector index)
[ ] Add deterministic regression tests for docs discovery against known COM/VBA symbols
```

**Status**: ✅ Tool Created | ⏳ Tests Added | ⏸️ RAG Backend Deferred

## Platform Matrix

| Platform | COM Access | VBA Index | Status |
|----------|-----------|-----------|--------|
| Windows 11 + SolidWorks | ✅ Yes | ✅ Yes | ✅ Fully Supported |
| WSL 2 (Linux subsystem) | ❌ No | ❌ No | ⏸️ Not Supported |
| Windows (Sandbox/VM) | ✅ Yes (with passthrough) | ✅ Yes | ⚠️ Limited |
| macOS | ❌ No (no SolidWorks) | ❌ No | ❌ Not Applicable |
| Linux (native) | ❌ No (no SolidWorks) | ❌ No | ❌ Not Applicable |

## Deployment Checklist

- [x] Core indexer implemented (SolidWorksDocsDiscovery class)
- [x] MCP tool registration complete
- [x] PowerShell dev command added (dev-docs-discovery)
- [x] JSON export working
- [x] Unit tests added (4 tests)
- [x] Documentation complete
- [ ] RAG backend integration (future)
- [ ] Semantic search interface (future)
- [ ] Auto-refresh on version change (future)
