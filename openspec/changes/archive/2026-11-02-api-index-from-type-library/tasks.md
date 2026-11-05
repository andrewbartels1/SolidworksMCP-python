## 1. Type library reader

- [x] 1.1 New `src/solidworks_mcp/tools/type_library.py`: `index_type_library(lib)` walks every `TKIND_DISPATCH` interface into the member records of design decision 3 (kind, description, parameters with VBA type names and `in`/`out`/`in_out`, return type resolved to interface names, merged property access); skips COM plumbing and `_` names
- [x] 1.2 Same module: `registered_versions(winreg=...)` parses the hex version keys under `HKCR\TypeLib\{83A33D31-...}`; `choose_version(registered, year)` picks by year (`major + 1992`) or the newest; `load_type_library(year, pythoncom=..., winreg=...)` returns `(lib, info)` with guid, version, year and path, or raises a typed error naming the reason and the installed years
- [x] 1.3 `tests/solidworks_mcp/tools/test_type_library.py` with a fake type library and a fake `winreg`/`pythoncom`: methods vs properties, merged get/put access, `in_out` params, array and pointer types, unmapped type → `Variant`, plumbing skipped, version parsing and choice, each error reason

## 2. Discovery and index format

- [x] 2.1 `docs_discovery.py`: delete `_KNOWN_SW_INTERFACES`, `_enumerate_typeinfo_members`, `_discover_com_via_typeinfo`, `connect_to_solidworks` and the `IModelDoc2_active` supplement; `discover_all()` builds `com_objects` from the type library and keeps the VBA scan; index `version` "2.0" with the `type_library` block
- [x] 2.2 `discover_solidworks_docs`: no SolidWorks-running check; a load failure becomes `ToolOperationError` with the reason; message and payload shape unchanged
- [x] 2.3 Replace the catalogue, typeinfo and `IModelDoc2_active` tests in `tests/solidworks_mcp/tools/test_docs_discovery.py` with tests for the new discovery path (fake loader)

## 3. Lookups

- [x] 3.1 Index loading treats a missing index or a `version` other than "2.0" as unusable, builds and saves a fresh one, and reports `index_status` (`ready` / `rebuilt` / `unavailable`) and `type_library_version` in all four lookup/search responses; an unusable old index is never answered from
- [x] 3.2 `_lookup_method` returns the library's spelling plus `parameters`, `return_type`, `description`, `signature_indexed: True`; `unavailable` answers `found: False` with the reason in `note`
- [x] 3.3 `auto_discover_if_missing` stays accepted; its description says it is no longer needed
- [x] 3.4 Tests for each spec scenario under "Lookups build or replace an out-of-date index themselves" and the casing and `OpenDoc6` direction scenarios (fake type library)

## 4. Docs

- [x] 4.1 `docs/user-guide/tool-catalog/docs-discovery.md`: prerequisite is SolidWorks installed (not running); `lookup_api_method` returns signatures; lookups build the index themselves
- [x] 4.2 CHANGELOG `Unreleased` → Fixed: API lookups answer from the SolidWorks type library (#195); note the old index is rebuilt automatically and the built-in name list is gone

## 5. First verification

- [x] 5.1 ruff, the non-live suite at 100% coverage, strict docs build

## 6. The year at start-up (design 7)

- [x] 6.1 `server.py`: `--year` option on `cli` and the legacy `main()` parser, setting `config.solidworks_year`; `_run_with_config` logs one warning when not mock and no year is set
- [x] 6.2 `setup/launcher.py`: `server_command(mock, year)` appends `--year <year>` to real entries; `setup/cli.py`: `--year` option, `_choose_year` (given year must be installed, else exit 1 naming installed years before any write; default newest; none for mock)
- [x] 6.3 `docs_discovery.py`: delete `_detect_installed_solidworks_year`; the year comes from the call, then the config, then the newest type library
- [x] 6.4 Tests: CLI option and warning, `server_command` with a year, setup year choice (default, override, not installed, mock)

## 7. Index reuse (design 8)

- [x] 7.1 `type_library.py`: `target_version(year, strict, registry)` split out of `load_type_library`
- [x] 7.2 `_index_for_lookup` reads the index named for the target version, reuses it when format and `type_library.version` match, else rebuilds; explicit `index_file` answered from directly; responses' `year` from the answering library
- [x] 7.3 `save_index` raises `ToolOperationError` naming the path on a write failure
- [x] 7.4 Tests: three lookups build once; a different library version rebuilds; explicit file needs no registry; the root conftest also blocks `target_version`

## 8. Uniform contracts and descriptions (design 9, 10)

- [x] 8.1 `type_library.py`: Pydantic `ApiParameter`, `ApiMethod`, `ApiProperty`, `ApiInterface`, `TypeLibraryInfo` with `Literal` direction/access and field descriptions; `TypeLibLike` / `TypeInfoLike` protocols; full docstrings on the helpers
- [x] 8.2 `docs_discovery.py`: Pydantic `MemberLookup`, `InterfaceLookup`, `SearchMatch`, `RelatedMember`, `RelatedLookup`; tools return `model_dump(exclude_unset=True)`; `_IndexForLookup.status` a `Literal`
- [x] 8.3 Inputs: shared `ApiIndexInput` base (`year` 1995–2100, `index_file`), real field descriptions and Attributes docstrings; `DiscoverDocsInput.year` describes what it picks; `include_vba=False` skips the VBA scan
- [x] 8.4 Tool docstrings in the `verify_model` style (needs, nothing to call first, `index_status`, `note`, Args, Returns, Example); RAG rebuild moved to `_rebuild_rag_index()`; `time` imported once; `FastMCP` / `SolidWorksAdapter` hints; drop the per-tool `type: ignore`; fix stale text (names-only docstring, fallback "run discover", Gemma comment, "coherent guidance")
- [x] 8.5 Tests updated for the models; a test that every docs tool's listed description names its setup and every input field has a description

## 9. Docs

- [x] 9.1 README, installation, quickstart and client setup pages: `--year` in every config, documented as required for real SolidWorks; tool catalog page and generator text match the new descriptions
- [x] 9.2 CHANGELOG: `--year` (Added), lookups rebuilding every call (Fixed), `include_vba` honoured (Fixed)

## 10. Verify and sign off

- [x] 10.1 ruff, the non-live suite at 100% coverage, strict docs build, `openspec validate --strict`
- [x] 10.2 Live demo `tests/live/test_live_sw_api_lookup.py` through `fastmcp.Client` with `evidence(...)`: the description an agent sees; cold start then reuse; `OpenDoc6` and `SaveBMP` signatures; made-up member and casing note; `InsertFeatureChamfer` on `IFeatureManager` not `IModelDocExtension`, then `add_chamfer` on a scratch part; the not-installed year. Run one at a time with `live_demo.ps1`, with the user's permission
- [x] 10.3 PR closing #195 (#200)
