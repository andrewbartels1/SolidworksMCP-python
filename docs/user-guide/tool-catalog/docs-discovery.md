# Docs Discovery Tools

Look up SolidWorks API interfaces, methods and properties, with each member's parameters, return type and description. Everything is read from the SolidWorks type library installed on this machine, so the answers match your SolidWorks version and nothing is hand-typed.

> **Prerequisite:** SolidWorks installed (it need not be running), on Windows with pywin32.
>
> Nothing has to be run first. The lookup tools build the index the first time they run (about a second) and reuse it after that, rebuilding it only when SolidWorks is upgraded or the index was written by an older version. Without a SolidWorks type library on the machine they answer "no match" and say why in `note`.
>
> The year comes from the server's `--year` start-up argument (setup writes it), else the newest installed SolidWorks. Every response reports the `year` and `type_library_version` that answered, and `index_status`: `ready` (saved index), `rebuilt` (built for this call) or `unavailable`.

**Total tools in this category: 5**

---

### `discover_solidworks_docs`

Rebuild the index on purpose; the lookups don't need it. It reads every interface in the installed SolidWorks type library, plus the VBA library references, and never starts or calls SolidWorks. The response carries a summary, the type library it read and the saved file, not the index itself.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `year` | `int?` | — | `null` | SolidWorks year whose type library to read; an error if it isn't installed. Unset: the server's `--year`, else the newest installed |
| `include_vba` | `bool` | — | `true` | Also list the VBA type libraries registered on this machine |
| `output_dir` | `str?` | — | `null` | Folder to save the index in; the lookups only read the default folder |

**Prerequisite:** SolidWorks installed (it need not be running), Windows only

**Sample call:**

```json
{}
```

---

### `search_solidworks_api_help`

Search interface and member names by keyword when you don't know the exact name: `chamfer` finds `IFeatureManager.InsertFeatureChamfer`. Then call `lookup_api_method` on a match for its parameters. The response also suggests MCP tools for the task (`fallback_help`).

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | `str` | ✅ | | Words to find in interface and member names |
| `year` | `int?` | — | `null` | SolidWorks year to answer for; usually unset (the server's `--year`) |
| `max_results` | `int` | — | `10` | Maximum number of results (1–50) |
| `index_file` | `str?` | — | `null` | A saved index to answer from instead, e.g. copied from another machine |
| `auto_discover_if_missing` | `bool` | — | `false` | No longer needed; still accepted |

**Sample call:**

```json
{
  "query": "chamfer",
  "max_results": 5
}
```

---

### `lookup_api_interface`

List every indexed member (methods and properties) of a COM interface. Purpose-built for "give me the full surface of `IFeatureManager`" — more reliable than parsing full-text search results when you already know the interface name.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `interface` | `str` | ✅ | | COM interface name, e.g. `ISldWorks` |
| `year` | `int?` | — | `null` | SolidWorks year to answer for; usually unset (the server's `--year`) |
| `index_file` | `str?` | — | `null` | A saved index to answer from instead, e.g. copied from another machine |

**Sample call:**

```json
{ "interface": "IFeatureManager" }
```

---

### `lookup_api_method`

Look up one method or property before calling it. Returns its name as SolidWorks spells it, its parameters (name, type, and direction: `in`, `out` meaning SolidWorks fills it, or `in_out` meaning pass a variable by reference), its return type and a one-line description. Names match regardless of case, as COM does; when your casing differs, `note` says so. A member that doesn't exist returns `found: false` with a `note`.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `interface` | `str` | ✅ | | COM interface name |
| `method` | `str` | ✅ | | Method or property name |
| `year` | `int?` | — | `null` | SolidWorks year to answer for; usually unset (the server's `--year`) |
| `index_file` | `str?` | — | `null` | A saved index to answer from instead, e.g. copied from another machine |

**Sample call:**

```json
{ "interface": "ISldWorks", "method": "OpenDoc6" }
```

---

### `find_related_api_members`

Given an indexed interface or member name, return related members: for an interface, its own members; for a member, the other members of every interface that also exposes it, plus name-substring matches elsewhere in the index.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | `str` | ✅ | | An indexed interface or member name |
| `year` | `int?` | — | `null` | SolidWorks year to answer for; usually unset (the server's `--year`) |
| `max_results` | `int` | — | `25` | Maximum related members to return (1–200) |
| `index_file` | `str?` | — | `null` | A saved index to answer from instead, e.g. copied from another machine |

**Sample call:**

```json
{ "name": "InsertSketch" }
```

---
