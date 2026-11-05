## Context

See proposal.md (Why) for the evidence. What the code does today:

- `SolidWorksDocsDiscovery.discover_com_objects()` attaches to the running
  SolidWorks (`GetActiveObject`). It reads `sw_app._oleobj_.GetTypeInfo()`
  for `ISldWorks` and the open document's type info, which it stores under
  `IModelDoc2_active`. Every other interface comes from
  `_KNOWN_SW_INTERFACES`.
- On this install the type-info read produced nothing. The saved index
  (`.generated/docs-index/solidworks_docs_index_2026.json`, format `1.0`)
  is the catalogue verbatim.
- The registered type library is `{83A33D31-27C5-11CE-BFD4-00400513BB57}`.
  Registry version keys are hex: `22.0` is major 34, which is SolidWorks
  2026. `pythoncom.LoadRegTypeLib(guid, 34, 0)` loads
  `...\SOLIDWORKS 3DEXPERIENCE R2026x\SOLIDWORKS\sldworks.tlb` without
  SolidWorks running. The library has 497 `TKIND_DISPATCH` interfaces, and
  `IModelDoc2` has 744 methods and 31 properties after the plumbing is
  filtered out.
- For each function, `GetNames(memid)` gives `[name, *param_names]`.
  `FUNCDESC.args` gives `(vartype, paramflags)` per parameter, `rettype`
  gives the return type, and `GetDocumentation(memid)[1]` gives a help
  string. For example, `OpenDoc6` has params
  `FileName, Type, Options, Configuration, Errors, Warnings`, and the last
  two have flags 3 (in|out).

## Goals / Non-Goals

**Goals:**

- One reader that turns a type library into the index, testable with a
  fake type library, so CI covers it without Windows.
- Lookups that are correct by construction, with nothing hand-typed.

**Non-Goals:**

- Enum values from `swconst.tlb` (issue #95).
- Indexing the SolidWorks help site or examples.
- Changing the VBA reference scan (`_discover_vba_references_via_registry`).
- Making `search_solidworks_api_help`'s scoring smarter. It keeps working
  over the `methods` / `properties` name lists.

## Decisions

### 1. Read the registered type library, never the running application

`type_library.py` lists registered versions by opening
`HKCR\TypeLib\{GUID}` and parsing each subkey as hex `major.minor`. It
loads one version with `pythoncom.LoadRegTypeLib(guid, major, minor)` and
reports the path with `QueryPathOfRegTypeLib`. The year maps as
`year = major + 1992`, the same mapping `_extract_year` already relies on.
It picks the version by the year the call requests, then the year the
server was started with (decision 7), then the newest registered.

*Alternative considered:* `sw_app._oleobj_.GetTypeInfo().GetContainingTypeLib()`.
It needs SolidWorks running. It also means a COM call to SolidWorks from a
tool, outside `_handle_com_operation` and its thread rules, and on this
machine `GetTypeInfo` already failed silently. Rejected.

*Alternative considered:* parse the pywin32 `gen_py` wrapper. It only
exists after makepy has run, it lags SolidWorks upgrades (runbook #2), and
it has no help strings. Rejected.

### 2. The reader is pure over a small protocol

`index_type_library(lib) -> dict` uses only `GetTypeInfoCount`,
`GetTypeInfoType`, `GetDocumentation(i)`, `GetTypeInfo(i)` and, on each
type info, `GetTypeAttr`, `GetFuncDesc`, `GetNames`, `GetDocumentation`
and `GetRefTypeInfo`. Tests pass a fake that implements exactly these. The
only Windows-only code is the small loader: the registry walk and
`LoadRegTypeLib`. Its tests use a fake `winreg`, and a fake `pythoncom` is
injected as a parameter, the way `launcher.find_uvx` takes `which`.

### 3. Member records

Each interface gets the following. The `methods` and `properties` lists
stay as they are, since `vector_rag.py` and `_search_index` read them.

```json
{
  "methods": ["OpenDoc6", "..."],
  "properties": ["ActiveDoc", "..."],
  "method_count": 0, "property_count": 0,
  "members": {
    "OpenDoc6": {
      "kind": "method",
      "description": "Opens an existing document",
      "parameters": [{"name": "FileName", "type": "String", "direction": "in"},
                     {"name": "Errors", "type": "Long", "direction": "in_out"}],
      "return_type": "IModelDoc2"
    },
    "ActiveDoc": {"kind": "property", "description": "...", "type": "Object", "access": "read"}
  }
}
```

- `invkind == 1` is a method. Property get, put and putref merge into one
  property record, with `access` set to `read`, `write` or `read_write`. A
  name that is both a method and a property (rare) is kept as a method.
- Types use VBA names (`String`, `Long`, `Double`, `Boolean`, `Variant`,
  `Object`, `Integer`, `Single`, `Date`, `Currency`, `Byte`), since
  SolidWorks' own help and our VBA generators use them. An array is shown
  as `Type()`. A pointer to a user-defined type resolves through
  `GetRefTypeInfo` to the interface name, such as `IModelDoc2`. Anything
  unmapped becomes `Variant`, so a missing mapping never fails the build.
- Direction: `PARAMFLAG_FIN` (1) alone is `in`, `PARAMFLAG_FOUT` (2) alone
  is `out`, both together are `in_out`, and neither is `in`.
- Plumbing (`QueryInterface`, `AddRef`, `Release`, `GetTypeInfoCount`,
  `GetTypeInfo`, `GetIDsOfNames`, `Invoke`) and names starting with `_` are
  skipped.

Index top level: `"version": "2.0"`, plus
`"type_library": {"guid", "version": "34.0", "year": 2026, "path"}`,
`"solidworks_version": "34.0"`, `com_objects`, `vba_references` and the
totals. A full index for SolidWorks 2026 is about 3 MB of compact JSON (it
is saved without indentation, since every lookup reads it). That is far too
big for a tool response, so `discover_solidworks_docs` returns a summary,
the `type_library` block and the saved file instead of the index.

### 4. Delete the catalogue and the running-app scan

`_KNOWN_SW_INTERFACES`, `_enumerate_typeinfo_members`,
`_discover_com_via_typeinfo`, `connect_to_solidworks` and the
`IModelDoc2_active` supplement are removed. `discover_all()` loads the type
library and the VBA references. When no type library can be loaded, it
raises a typed error, which the tool turns into a `ToolOperationError`
naming the reason ("not Windows", "no SolidWorks type library registered",
"SolidWorks <year> isn't installed; installed: ..."). That keeps the
response under the error boundary's usual shape.

*Alternative considered:* keep the catalogue, marked
`"source": "fallback"` (the issue's suggestion). 13 of 20 checked names
are wrong, and an agent tends to act on an answer even when it's flagged
"unverified". Rejected; no answer is better than a wrong one.

### 5. Lookups self-heal the index

`_load_index_for_lookup` and the search tool treat an index as unusable
when it is missing, or when its `version` isn't `"2.0"`. Either way they
try a build (decision 1) and save it under the existing file name. If the
build fails, they answer with `found: False` and an `index_status` of
`"unavailable"`, plus a `note` with the reason; they don't raise, since a
lookup's no-match is a normal result (spec: Unknown name). Responses gain
`index_status` (`"ready"`, `"rebuilt"` or `"unavailable"`) and
`type_library_version`. The existing age-based `_maybe_refresh_index`
(config-gated) stays as it is. `auto_discover_if_missing` stays on
`SearchApiHelpInput` with its description changed to say it's no longer
needed, so strict input validation doesn't reject old callers.

### 6. Real name and casing

`_lookup_method` already matches case-insensitively. With the type
library's names it returns `member` exactly as the library spells it
(`ViewZoomtofit2`), plus `parameters`, `return_type` and `description` from
`members`, and `signature_indexed: True`. The note about the index storing
names only goes away.

### 7. The year is a start-up argument, not a guess

The server gains `--year <YYYY>`, which sets `config.solidworks_year` (the
`SOLIDWORKS_MCP_SOLIDWORKS_YEAR` variable keeps working). Docs list it as
required for real SolidWorks. `_detect_installed_solidworks_year`, which
read folder names under `C:\Users\Public\Documents\SOLIDWORKS`, is deleted:
the folder can be missing, or left behind by an uninstalled version.

- Started for real SolidWorks without a year, the server logs one warning
  ("Start the server with --year, e.g. --year 2026, or rerun
  `solidworks-mcp-python setup`") and the lookups use the newest registered
  type library. A hard stop was rejected: every 1.5.0 client entry lacks
  `--year`, and uvx picks up new releases, so it would break working
  installs on upgrade.
- `setup` writes `--year <newest installed>` into each real entry, from
  `setup.solidworks.installed_versions()`. `setup --year 2025` overrides it,
  and a year that isn't installed stops setup before anything is written,
  naming the installed years. A mock entry gets no year. With no install
  found and `--yes`, the real entry is written without a year, and the
  server's warning covers it.
- `server_command(mock, year)` adds the flag, so the start-up check runs the
  same arguments the entry will.

Today the year only picks the type library. The adapter attaches to
whatever SolidWorks is running. A warning at connect when the running
version differs from `--year` would be useful, but it touches the adapter
and needs its own live regression run, so it is left for later.

### 8. Lookups find the index by the type library they would read

Decision 5 searched for `solidworks_docs_index_<guessed year>.json`, while
builds save under the type library's real year. When the two differed, or
no year was guessed, every lookup rebuilt and rewrote the 3 MB file (seen
with a fake library: three lookups, three builds). Now a lookup first asks
the registry which version it would load (`target_version(year, strict)`,
split out of `load_type_library`, with no library load), and reads
`solidworks_docs_index_<that year>.json`. The file is reused when its format
is `"2.0"` and its `type_library.version` matches; otherwise it is rebuilt.
An explicit `index_file` is answered from directly, with no registry read,
so a saved index also works on a machine without SolidWorks. The response's
`year` is the answering type library's year, not the guess. `save_index`
no longer swallows a write failure: it raises `ToolOperationError` naming
the path, since a silent `None` would mean a rebuild on every call.

### 9. Pydantic for records and results, dataclasses for plumbing

Data that ends up in the index file or a tool response becomes a Pydantic
model with `Field(description=...)`:

- in `type_library.py`: `ApiParameter`, `ApiMethod`, `ApiProperty` (a
  discriminated union on `kind`), `ApiInterface` and `TypeLibraryInfo`;
  `direction` is `Literal["in", "out", "in_out"]` and `access` is
  `Literal["read", "write", "read_write"]`;
- in `docs_discovery.py`: `MemberLookup`, `InterfaceLookup`, `SearchMatch`,
  `RelatedMember` and `RelatedLookup`.

Tools keep returning dicts, as every tool in the package does, built with
`model_dump(exclude_unset=True)`, so payload shapes don't change. The
index is saved with `model_dump()` and read back as plain JSON. A lookup
validates only the member it found, never the whole file, so there is no
per-call cost. `_IndexForLookup` stays a frozen dataclass, as internal
value objects are in 15 other modules, with `status` typed as
`Literal["ready", "rebuilt", "unavailable"]`. The type-library reader's
`Any` parameters become two small `Protocol`s (`TypeLibLike`,
`TypeInfoLike`), the protocol decision 2 already described.

The four lookup inputs share `ApiIndexInput(CompatInput)` for `year`
(bounded 1995–2100) and `index_file`, with descriptions that say where the
default comes from. `DiscoverDocsInput` keeps its own fields, and
`include_vba=False` now skips the VBA scan.

### 10. Tool descriptions carry the setup

An agent reads each tool's docstring as its description, so that is where
the setup goes: when to call it, what it needs (SolidWorks installed, not
running; nothing to call first), what `index_status` and a `found: false`
with `note` mean, the response fields, and one `Example input:`. FastMCP
gives the agent only the docstring's prose and drops its `Args:`,
`Returns:` and `Example:` sections, so all of this is written in the prose;
the sections stay for developers. A test reads the descriptions as a client
lists them. `src/utils/generate_tool_catalog.py` now finds an input model
annotated `Model | None` and includes fields from a base model defined in
the same module, so the catalog shows `year` and `index_file`. `discover_solidworks_docs` says it is only for rebuilding on
purpose. The RAG rebuild's `try/except` moves out of the tool into
`_rebuild_rag_index()`, per the error-boundary rule. Server-wide
instructions are issue #175's.

### 11. The demo goes through a real MCP client

`tests/live/test_live_sw_api_lookup.py` calls the tools with
`fastmcp.Client` over the in-memory transport, so each call is validated
and serialised the way a real client's is, and prints `evidence(...)` lines
for `live_demo.ps1`. Demos: the description an agent is given, cold-start
build then reuse, real signatures, the made-up member and casing cases, a
lookup that settles runbook #12 followed by a real `add_chamfer` on a
scratch part, and the not-installed-year failure.

## Risks / Trade-offs

- [The type library loads on a thread without COM initialized] → `pythoncom`
  initializes the importing thread, which is the event-loop thread that
  runs tools. Typelib loading goes through oleaut32 and doesn't create a
  SolidWorks object, so no apartment rule applies. The live test runs the
  lookup through the registered tool on the server's loop to prove it.
- [A machine with several SolidWorks versions registered] → the year picks
  the version. Responses report `type_library_version`, so a mismatch
  shows.
- [A version 1 index is the only one, on a non-Windows dev box] → lookups
  report `unavailable` instead of answering from it. That is a behaviour
  change for anyone who relied on the catalogue answers, which were mostly
  wrong. CHANGELOG notes it.
- [A larger index file] → about 3 MB, written once per version. It is
  loaded per lookup call, as today. Caching it in memory is a later
  optimization if it ever matters.
- [`vector_rag` chunking over many more members] → it chunks per interface,
  so the build takes longer but stays correct. It is only triggered by
  `discover_solidworks_docs`, as today.

## Migration Plan

No user action is required. The first lookup after upgrading rebuilds the
index from the type library. Rerunning `solidworks-mcp-python setup` adds
`--year` to existing client entries and silences the start-up warning. Rollback: revert the change, and the old reader accepts
the `"2.0"` file's `methods` / `properties` lists unchanged.
