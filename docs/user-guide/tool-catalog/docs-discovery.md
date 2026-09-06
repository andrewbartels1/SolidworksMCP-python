# Docs Discovery Tools

Introspect the live SolidWorks COM object library to discover available interfaces, methods, and properties for the installed version. Produces a JSON index that the integration harness uses to detect API-change drift between SolidWorks versions and suggest correct alternative tool calls.

> **Prerequisite:** SolidWorks running. win32com.client must be available (Windows only).

**Total tools in this category: 5**

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

### `lookup_api_interface`

List every indexed member (methods and properties) of a COM interface. Purpose-built for "give me the full surface of `IFeatureManager`" — more reliable than parsing full-text search results when you already know the interface name.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `interface` | `str` | ✅ | | COM interface name, e.g. `ISldWorks` |
| `year` | `int?` | — | `null` | SolidWorks year override |
| `index_file` | `str?` | — | `null` | Explicit path to a JSON index file |

**Sample call:**

```json
{ "interface": "IFeatureManager" }
```

---

### `lookup_api_method`

Confirm a method or property is indexed on an interface and return its sibling members for context. The local index stores member *names* only — full signatures (parameters, return type) are not available here; use `search_solidworks_api_help` or help.solidworks.com for those.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `interface` | `str` | ✅ | | COM interface name |
| `method` | `str` | ✅ | | Method or property name |
| `year` | `int?` | — | `null` | SolidWorks year override |
| `index_file` | `str?` | — | `null` | Explicit path to a JSON index file |

**Sample call:**

```json
{ "interface": "IFeatureManager", "method": "InsertFeatureChamfer" }
```

---

### `find_related_api_members`

Given an indexed interface or member name, return related members: for an interface, its own members; for a member, the other members of every interface that also exposes it, plus name-substring matches elsewhere in the index.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ | | An indexed interface or member name |
| `year` | `int?` | — | `null` | SolidWorks year override |
| `max_results` | `int` | — | `25` | Maximum related members to return (1–200) |
| `index_file` | `str?` | — | `null` | Explicit path to a JSON index file |

**Sample call:**

```json
{ "name": "InsertSketch" }
```

---
