# Docs Discovery Tools

Introspect the live SolidWorks COM object library to discover available interfaces, methods, and properties for the installed version. Produces a JSON index that the integration harness uses to detect API-change drift between SolidWorks versions and suggest correct alternative tool calls.

> **Prerequisite:** SolidWorks running. win32com.client must be available (Windows only).

**Total tools in this category: 2**

---

### `discover_solidworks_docs`

Discover and index SolidWorks COM and VBA documentation.

**Prerequisite:** SolidWorks running, win32com available (Windows only)

**Sample call:**

```json
{}
```

---

### `search_solidworks_api_help`

Search the SolidWorks API help index and return coherent guidance. Maps user intent to discovered COM members and practical MCP workflow guidance. Useful when a tool call fails or you need to find the correct API member name.

**Prerequisite:** A docs index exists (run `discover_solidworks_docs` first, or set `auto_discover_if_missing: true`)

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | `str` | ✅ | | Search phrase for SolidWorks API help (methods, properties, objects) |
| `year` | `int?` | — | `null` | SolidWorks year override (e.g. 2026) |
| `max_results` | `int` | — | `10` | Maximum number of results (1–50) |
| `index_file` | `str?` | — | `null` | Explicit path to a JSON index file |
| `auto_discover_if_missing` | `bool` | — | `false` | Auto-generate the docs index if none is found |

**Sample call:**

```json
{
  "query": "SelectByID2",
  "max_results": 5,
  "auto_discover_if_missing": true
}
```

---
