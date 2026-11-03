## Why

The API lookup tools (`lookup_api_method`, `lookup_api_interface`,
`find_related_api_members`, `search_solidworks_api_help`) answer from a docs
index that, on a real SolidWorks 2026 install, is built entirely from a
hand-typed catalogue in `tools/docs_discovery.py`. That catalogue is wrong
often enough to mislead an agent in both directions: it says
`IModelDoc2.SaveBMP` doesn't exist (it does) and that
`IModelDoc2.SaveBitmapWithVariableSize` does (it doesn't). Issue #195.
(The issue's `ViewZoomToFit2` row is a casing difference: SolidWorks spells
it `ViewZoomtofit2`, and COM matches names regardless of case, so both
spellings work. The lookups report the real spelling.)

Checked against the registered type library on this machine:

- The index on disk holds 100 methods across 12 interfaces, exactly the
  catalogue's counts. Even `ISldWorks` came from the catalogue, so the live
  scan has never contributed anything here.
- 13 of the 20 `IPartDoc` and `IFeatureManager` names in the catalogue don't
  exist in SolidWorks 2026, and one catalogue interface (`IExtensionManager`)
  isn't a SolidWorks interface at all; the real one is `IModelDocExtension`.
- The scan only ever read `ISldWorks` and the open document (stored under
  `IModelDoc2_active`), so `IModelDoc2` itself could only ever come from the
  catalogue.

The registered type library holds all 497 SolidWorks dispatch interfaces, and
for every member its parameter names, types, which parameters are outputs,
the return type and a one-line description. The current spec already
promises parameters and a return type from `lookup_api_method`. The code
never delivered them.

## What Changes

- The docs index is built from the registered SolidWorks type library,
  loaded by its GUID. It covers every dispatch interface, with a signature
  and description per member. It no longer reads the running application's
  type information or the open document.
- Building the index no longer needs SolidWorks running, only installed.
  The type library is the one for the year the call asks for, else the year
  the server was started with, else the newest registered one. The year is
  never guessed from folder names any more.
- The server takes a `--year` start-up argument (for example
  `uvx solidworks-mcp-python --year 2026`), documented as required for real
  SolidWorks. `setup` writes it into each client entry, reading the
  installed year from the registry. Started without it, the server logs a
  warning saying how to add it and uses the newest installed SolidWorks, so
  entries written by 1.5.0 keep working. Mock mode needs no year.
- Lookups find a saved index by the type library they would read, so they
  build it once, not on every call. Before this, a year guess that missed
  (no `Public\Documents\SOLIDWORKS <year>` folder, or a leftover older one)
  rebuilt and rewrote the 3 MB index on every lookup. Responses report the
  year of the type library that answered.
- **BREAKING (index file format):** the index moves to format version 2.
  Each interface keeps its `methods` and `properties` name lists, which other
  readers use, and gains a `members` map holding each signature. A version 1
  index on disk is treated as out of date and rebuilt.
- The hand-typed `_KNOWN_SW_INTERFACES` catalogue is deleted. With no type
  library there is no index, and the lookups say so plainly instead of
  answering from guesses. (The issue suggested keeping it marked as a
  fallback; the check above shows it is mostly wrong, so marking it would
  still mislead.)
- `lookup_api_method` returns the member's real name and casing, its
  parameters (name, type, input or output), return type and description, and
  says which type library answered.
- The lookups and the search build the index themselves when it is missing
  or out of date, because building now only reads a file on disk.
  `auto_discover_if_missing` is still accepted, so existing callers aren't
  rejected, but it is no longer needed.
- **BREAKING (`discover_solidworks_docs` response):** the response no longer
  includes the whole index, which is now megabytes. It returns the summary,
  the type library it read and the saved file; the lookup tools read the
  file.
- COM plumbing names (`QueryInterface`, `AddRef`, `Invoke` and so on) are no
  longer listed as SolidWorks methods.
- Index records and lookup results become Pydantic models with typed,
  described fields (`direction` and `access` are `Literal`s), in line with
  the rest of the package. Tools still return plain dicts, built with
  `model_dump()`, so payload shapes are unchanged. The input models share
  one base for `year` and `index_file`, with real descriptions.
  `discover_solidworks_docs` honours `include_vba`, which it ignored.
- Each tool's description, which is what an agent reads, says what it needs
  (SolidWorks installed, not running), that the first call builds the index
  and later calls reuse it, what `index_status` means, and that a no-match
  carries a `note` saying why. Server-wide guidance stays with issue #175.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `tools/api-help-lookup`: lookups answer from the type library, return real
  signatures, report their source, work without SolidWorks running, say
  plainly when no index can be built, reuse the saved index, and describe
  their setup to the agent.
- `setup/client-setup`: the server takes `--year`; setup writes it.
- `docs/readme-install`: the documented client configs pass `--year`.

## Impact

- `src/solidworks_mcp/tools/docs_discovery.py`: discovery rewritten around a
  new type-library reader; catalogue and running-app scan deleted; lookup
  helpers return signatures; index loading treats version 1 as out of date.
- New `src/solidworks_mcp/tools/type_library.py`: reads the registered type
  library into the index format (pure functions over an `ITypeLib`-like
  object, so unit tests use a fake).
- `src/solidworks_mcp/agents/vector_rag.py` reads `methods` / `properties`
  per interface; these stay, so it keeps working. It may also use the new
  descriptions, though that isn't required.
- No adapter changes: `pywin32_adapter.py`, `base.py` and `mock_adapter.py`
  are untouched. The type library is a file read through `pythoncom`. It is
  not a call into SolidWorks, so the STA and settle-pause rules don't apply.
  No SolidWorks object is created or called.
- Tests: `tests/solidworks_mcp/tools/test_type_library.py` (new) and
  `test_docs_discovery.py` (catalogue and `IModelDoc2_active` tests
  replaced). A live test checks the issue's four members and the `OpenDoc6`
  signature against the real registered type library.
- `src/solidworks_mcp/server.py`: `--year` option and the missing-year
  warning. `src/solidworks_mcp/setup/cli.py` and `launcher.py`: setup
  chooses the year and writes `--year`.
- Docs: `docs/user-guide/tool-catalog/docs-discovery.md` (prerequisite and
  `lookup_api_method` description); README, installation, quickstart and
  client setup pages (`--year` in every config); a CHANGELOG entry.
- A live demo, `tests/live/test_live_sw_api_lookup.py`, calls the tools
  through a real MCP client and prints evidence, for sign-off with
  `tests/scripts/live_demo.ps1`.
