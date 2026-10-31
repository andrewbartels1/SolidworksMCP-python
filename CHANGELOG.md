# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Version history splits in two: the `3.x` entries at the bottom are the
> original TypeScript/winax implementation. The project is now a Python +
> pywin32 MCP server and restarted its own versioning at `1.0.0`; `1.x`
> entries are the current line.

## [Unreleased]

### Added

- **Demos page** in the docs: every demo GIF with what it checks, its
  prompt, its tool calls (all 58, with arguments, for the README demo) and
  the test that made it. The README's Demos section shows the GIFs in a
  grid, each linking to its entry.

GD&T on drawings (first step of #182):

- **`add_gtol`** adds a feature control frame (position, flatness,
  perpendicularity, parallelism, surface profile, concentricity) with a Ø
  zone, a material condition and up to three datums. It goes on a drawing
  dimension (the usual place for a hole's position tolerance), on an edge
  with a leader, or free on the sheet. The frame is read back, so one
  SolidWorks did not fill in is an error.
- **`add_datum_tag`** puts a datum feature symbol (A, B, C, ...) on a drawing
  edge.

Drawing layout:

- Each model dimension is kept in the view that shows most of the model's
  dimensions, so a plate sketched on Top is dimensioned in its plan rather
  than edge-on in the front view.
- A diameter or radius leader stays on its feature when its text is moved,
  and its text steps outward from the feature; a leader no longer runs
  through another dimension's text.
- The layout re-plans, from the real geometry, whatever is still in
  conflict after the first pass (up to three passes).
- `insert_bom_table` slides a table placed by the sheet's anchor back onto
  the sheet (`moved_onto_sheet`).
- Dimensions that do not touch share a row: the hole positions at each end
  of a plate sit in one row, its overall length in the next.
- A dimension's text width counts each SolidWorks code (`<MOD-DIAM>` for
  Ø) as one symbol, not as ten characters.
- `generate_drawing_package` lays the dimensions out again on the finished
  sheet, clear of each view's caption and note as drawn, before checking it.
- `add_gtol` on a dimension lays the view out again with the frame counted
  as part of that dimension, so the frame does not land on its neighbours.
- `generate_drawing_package` takes `include_bom` (assemblies): the BOM goes
  in the top of the isometric view's cell, with the isometric fitted below.
- `generate_drawing_package` draws the front, plan and side views with hidden
  lines visible (dashed), so through holes show in the front and side views;
  `hidden_lines_visible` reports each view as read back.
- A hole note with its GD&T frame may sit inside the part, near its hole on a
  short leader, when it is well inside the view and clear of every feature
  the dimensions start from; `add_gtol` tries there first. The overlap check
  allows the same and nothing else inside a view.
- Notes inside views (SolidWorks puts a caption into the active view) are
  kept clear of, as well as notes on the sheet.
- On an assembly, `generate_drawing_package` leaves the model's own
  Material property alone: a link to an assembly's material showed
  "<not specified>".
- View captions read FRONT VIEW, TOP VIEW, SIDE VIEW and ISOMETRIC VIEW
  (were FRONT ELEVATION, PLAN, SIDE ELEVATION, ISOMETRIC).
- `add_gtol` finds a part's dimension on an assembly drawing, where its name
  can carry the component (`D3@Sketch1@Demo Plate-1@...`).
- The README opens with a recorded demo: a prompt answered in 58 tool calls,
  from sketch to an assembly drawing with GD&T and a BOM.
  `tests/scripts/live_demo.ps1 -Record` records a live test (changed frames
  only, captions as each step starts) and builds a sped-up GIF.

Model verification (#173):

- **`verify_model`** checks the active part or assembly against what you
  expected, in one call. It covers mass and volume within a tolerance,
  overall size, feature count and solid-body count; for assemblies also
  component count, mate count and no interference. Each check reports
  expected, actual and pass/fail. A value that cannot be measured reports
  `null`, never a pass. With no expectations it reports what it measured.
- **`measured_change`** on `create_extrusion`, `create_revolve` and
  `create_cut_extrude`: volume, overall size and body count before and after
  the feature. A feature that succeeds without changing the volume gets a
  `warning`.
- New adapter read `get_model_geometry_summary`: bounding box from each
  body's exact extreme points, solid-body count, volume, component and mate
  counts. It never rebuilds the model or clears the selection.

Packaging (#172):

- **PyPI and MCP Registry release.** Pushing a `v*` tag builds the package,
  publishes it to PyPI, creates the GitHub Release from this changelog and
  publishes `server.json` to the official MCP Registry. Both registries use
  the workflow's GitHub identity; no tokens are stored.
- **`uvx solidworks-mcp-python`** runs the server without cloning the repo
  (new `solidworks-mcp-python` entry point alongside `solidworks-mcp`).
- The server now reports the package version to MCP clients instead of
  FastMCP's default.

Engineering-data tools, contributed by @SaiqKamran (#117) and signed off live
against SolidWorks 2026:

- **`list_model_dimensions`** (#131): every dimension's editable full name
  (`D1@Sketch1`), value and system value, optionally for one feature.
- **`measure_entities`** (#132): area, perimeter, length, radius, distance
  and angle of one or two faces, edges or vertices.
- **`get_material`** (#133) and **`set_material`** (#134): read and assign a
  part's library material; the assignment is read back, and an unknown name
  is `not_found`.
- **`list_available_materials`** (#135): search the configured and built-in
  `.sldmat` libraries.
- **`get_custom_properties`** (#136) and **`set_custom_property`** (#137):
  read and write title-block/BOM properties, with resolved `$PRP:` values.
- **`export_flat_pattern`** (#138): a sheet-metal part's flat pattern to DXF
  or DWG.

Drawing-dimension tools, also contributed by @SaiqKamran (#117) and signed
off live against SolidWorks 2026:

- **`insert_model_dimensions`** (#144): the model's dimensions on the active
  drawing's views, each shown once; pictorial views are skipped unless named.
- **`arrange_dimensions`** (#145): moves dimensions outside the views in rows
  and checks the real geometry for overlaps; any that remain are listed in
  the error.

Drawing-package tools, the last part of @SaiqKamran's #117:

- **`insert_bom_table`** (#148): a bill of materials for an assembly drawing
  view (top-level, parts-only or indented), snapped to the sheet's BOM anchor
  with the library `bom-standard` template by default.
- **`set_sheet_scale`** (#149): sets the active sheet's scale and reads it back
  from the sheet.
- **`generate_drawing_package`** (#150): a complete A3 drawing of a part or
  assembly in one call: ISO sheet format, third-angle views plus an isometric
  at the largest standard scale that fits, model dimensions shown once and laid
  out with `arrange_dimensions`, a filled title block, view captions and a
  NOTES block, checked for overlaps on the read-back geometry, saved as
  `<drawing number>.SLDDRW` plus a PDF.

### Fixed

Found in the live sign-off of the drawing-package tools on SolidWorks 2026:

- **`generate_drawing_package`** builds the sheet in separate COM steps
  (sheet, views, layout, dimensions, notes, check, title block), each followed
  by the settle pause; one long burst of drawing calls is the pattern that
  crashed SolidWorks 2026 (COM pitfall #26).
- **`generate_drawing_package`**: the DWG NO. and TITLE are shrunk to fit
  their title-block boxes, so a long drawing number no longer runs into the
  size box. A field that still does not fit is reported as an overlap. The new
  `title_block_text_height_mm` option sets a smaller text height.
- **`insert_bom_table`**: the table grows up from its bottom-left corner, so
  on a sheet with no format it no longer hangs below the sheet. The result
  includes the table's box, and a table that runs off the sheet is an error.

## [1.4.0] - 2026-10-22

Minor release. New tools and a uniform error contract; every change is
additive for MCP clients. Every new tool and fix was signed off live against
SolidWorks 2026.

### Added

- **`select_feature`** (#106): select a feature, sketch or plane by name
  (bare or `Name@Part`, optional append).
- **`select_face_edges`** (#119): find a face by side, point or reference
  plane and select its edges, optionally only circular or linear ones.
  Chains into `add_chamfer(edge_names=[])`.
- **`rebuild_model`** (#106): `ForceRebuild3` plus the feature errors
  SolidWorks reports, each with severity, error code, parent features and a
  hint.
- **`list_drawing_views`** (#106): the active drawing's view names.
- **Error contract** (#123): every tool runs inside one error boundary, and
  every error payload carries `error_type` and an actionable `hint` alongside
  `status`, `message` and `execution_time`. The categories are listed in the
  tool catalog.
- **Live demo runner** (#127): `tests/scripts/live_demo.ps1` runs one live
  test and prints its `[evidence]` lines.

### Fixed

- `exit_sketch` closes a sketch left open in SolidWorks even when the server
  lost track of it (#120).
- COM calls from the wrong thread are refused with a clear
  `com_wrong_thread` error instead of a cryptic `AttributeError` (#121).
- `create_drawing` falls back to a blank A-size drawing when no template is
  configured (#122).
- A short settle pause after every COM operation; back-to-back calls crashed
  SolidWorks 2026 in its idle-time refresh.

### Changed

- `save_assembly(include_references=True)` copies the assembly and its
  dependencies directly. Its tool-layer Pack-and-Go never worked on
  SolidWorks 2026 and was removed, along with the `native_pack_and_go_error`
  response field (#125).
- Depends on `pydantic-ai-slim[openai,anthropic,mcp]` instead of the full
  `pydantic-ai`; the server only uses those providers (#126).
- Docs build with `strict: true`; `mkdocs` is pinned below 2 (#46).
- Honest 100% coverage with no `# pragma: no cover`, and a test tree that
  mirrors `src/` (#124).

### Security

- `certifi` 2026.10.19 (drops compromised emSign roots), `pillow` 13.0.0,
  `virtualenv` 21.14.13; `aiohttp` is no longer a dependency (#126).

Tool count 134 → 138.

## [1.3.0] - 2026-10-13

Minor release.

### Added

- **`add_chamfer` tool** (#110): equal-distance chamfers on named or
  currently selected edges, wired through every adapter layer.
- **`get_selected_entities` tool** (#112): read which faces, edges and
  vertices are highlighted in the live SolidWorks UI, with their geometry.

### Fixed

- `create_cut_extrude` works again: the real `FeatureCut3` signature, and an
  explicit or tree-verified sketch instead of a guessed one (#109).
- The circuit breaker is per operation, so one failing tool no longer blocks
  the others (#109).
- `auto_center_marks` counts centre marks with the correct
  `swAnnotationType_e` value on R2026x (#107).
- `export_image` captures its own document's window, not whichever one is in
  front (#112).

### Security

- Pinned transitive `httpx2`/`httpcore2` and bumped `uv.lock` past the
  October 2026 Trivy CVEs; Dependabot added (#108, #111).

Tool count 132 → 134.

## [1.2.0] - 2026-09-06

Minor release — new tools, all additive and backward compatible. All three
verified live against SolidWorks 2026.

### Added

- **`create_reference_point` tool** (#58) — reference points on the active
  part: `along_curve` (a point on the edge under a coordinate, at a distance
  or percentage of its length) or `face_center`. Completes the reference-
  geometry set alongside `create_reference_plane` / `create_axis`.
- **`save_body_as_part` tool** (#62) — extract one named solid body from a
  multibody part to a standalone `.sldprt` via `CreateSaveBodyFeature`; the
  response lists every solid body found so an unknown name reports the real
  options.
- **`auto_center_marks` tool** (#63) — run SolidWorks' automatic centre-mark
  insertion (holes / fillets / slots) on a named drawing view, reporting the
  centre-mark count before and after.
- **Tutorial: "Smart Dimensions, Reference Points, Save Bodies & Centre
  Marks"** — a prompt-driven walkthrough of the three new tools plus
  `add_sketch_dimension`, captured from a live SolidWorks 2026 MCP session
  (real `export_image` screenshots), with the exact prompt text and the
  tool-call sequence each prompt produces.

Tool count 129 → 132. Also corrects a long-stale `drawing.py` tool count
(reported 8, 12 tools were actually registered → now the true 13).

## [1.1.0] - 2026-09-06

Minor release — new tools, all additive and backward compatible.

### Added

- **`rename_feature` tool** (#59) — rename a feature on the tree via the
  settable `IFeature.Name` property, with read-back verification and a
  name-collision guard. Wired through every adapter layer with mock + tool
  tests and `tests/test_live_sw_wave2.py`; verified live against SW 2026.
- **`set_units` tool** (#60) — set the document linear unit system
  (`mm`/`cm`/`m`/`in`/`ft`, plus aliases). Sets `swUnitSystem` and reads it
  back from the document to confirm adoption; the swconst integers were
  transcribed from a live `swconst.tlb` (the published API help omits them).
  `create_part`'s previously-ignored `units` parameter now routes through
  the same helper.
- **`list_open_documents` / `activate_document` tools** (#61) —
  `list_open_documents` is a read-only `ISldWorks.GetDocuments` enumeration
  (`title`, `path`, `type`, `is_active`); `activate_document` resolves a
  target by title / path / file name, calls `ActivateDoc3`, and verifies
  against `ActiveDoc`.
- **Granular API-lookup tools** (#64) — `lookup_api_method`,
  `lookup_api_interface`, `find_related_api_members` in the docs-discovery
  layer (`lookup_api_enum` split to a follow-up).
- **SoC `script_line` capture** (#28) — every `ToolCallRecord` now stores the
  rendered SolidWorks-as-Code line at write time; a startup `ALTER TABLE`
  check backfills the column on existing local databases.
- **Config toggles** — `SOLIDWORKS_MCP_SOC_LOGGING_ENABLED` (off by default)
  and `SOLIDWORKS_MCP_DOCS_INDEX_AUTO_REFRESH` (on, 21-day staleness).

### Fixed

- Tools that read `adapter.currentModel` now resync from `ISldWorks.ActiveDoc`
  first (shared `_sync_current_model_from_active`, factored out of the #91
  fix), so `set_units` / `rename_feature` / `get_model_info` work for
  documents opened in the SolidWorks UI rather than through a tool.

## [3.1.0] - 2026-03-11

### Fixed
- **Critical: SelectByID2 Type Mismatch** (Issue #8) - Replace `null` with `undefined` for COM optional parameters across all `SelectByID2` and `SaveAs` calls. COM interprets `null` as VT_NULL which causes DispInvoke type mismatch errors.
- **Sketch Selection Strategy** - Prioritize feature tree traversal (`FeatureByPositionReverse` + `GetTypeName2`) over `SelectByID2` for sketch selection. This approach is more reliable and avoids COM selection issues entirely.
- **Mass Properties Null Safety** - Add null coalescing guards in analysis tools to prevent `TypeError` when calling `.toFixed()` on sketch-only documents that return null for numeric properties.

### Removed
- Dead refactored modules (`index.refactored.ts`, `modeling-refactored.ts`, `api-refactored.ts`, `tsconfig.refactored.json`) that were never integrated
- Incomplete clean architecture directories (`src/application/`, `src/commands/`, `src/infrastructure/`) that added complexity without being wired into the server
- Duplicate `.eslintrc.json` (project uses `eslint.config.js` flat config)
- Unused package.json scripts (`build:refactored`, `dev:refactored`, `start:refactored`, `migrate`)

### Added
- `CLAUDE.md` project guide for AI contributors

### Changed
- Moved 7 analysis/architecture docs from repo root to `docs/` directory
- Updated package.json description and keywords to reflect actual architecture

## [3.0.9] - 2025-09-10

### Fixed
- **Critical: Winax Module Loading** - Reverted to simple ES module import pattern that matches working version
- **COM Object Access** - Fixed GetTitle/GetType/GetPathName property access on Document objects
- **Part Creation** - Use NewPart() method instead of NewDocument() with template

### Changed  
- **Installation Method** - Documented that local installation is required due to winax native module compilation
- **README Documentation** - Added clear warnings and explanations about winax installation requirements

### Technical
- Removed complex eval-based winax loading in favor of direct import
- Cleaned up test files and debugging artifacts
- Updated documentation to reflect installation limitations

### Known Issues
- Global npm installation does not work due to winax native module requirements
- Each Windows system must compile winax locally during npm install

## [3.0.8] - 2025-09-10

### Fixed
- **COM Object Method Access** - GetTitle/GetType are properties on Document objects, not Application
- **Part Creation** - Added fallback to NewDocument when NewPart fails

## [3.0.1 to 3.0.7] - 2025-09-10

### Fixed
- Multiple attempts to fix winax module loading and COM object creation
- Winston logger file-only output to prevent MCP protocol corruption
- Zod schema to JSON schema conversion for Claude Desktop tool visibility

## [2.2.0] - 2025-08-19

### Fixed
- **Critical: Handlebars Helper Registration** - Added all necessary Handlebars helpers (eq, ne, lt, gt, lte, gte, and, or, not) to fix VBA generation tools
- **Template Name Mismatch** - Fixed batch_export template mapping and created proper batch_export.vba template
- **Rebuild Model API** - Updated to use correct SolidWorks API methods (ForceRebuild3, EditRebuild, Rebuild) with fallback strategies
- **Close Model Error Handling** - Added safe error handling for title retrieval preventing COM object access errors
- **Export File Robustness** - Enhanced export functionality with format-specific handling and retry logic
- **Mass Properties Extraction** - Improved getMassProperties with comprehensive error handling

### Added
- batch_export.vba template for batch export operations
- Debug scripts (debug-server.mjs, debug-wrapper.mjs, test-fixes.mjs) for troubleshooting
- SWChecklist.md comprehensive testing checklist
- zod-to-json-schema dependency for schema validation
- ensureCurrentModel helper method in api.ts

### Improved
- Enhanced error handling across all API methods with multiple fallback strategies
- Better COM object access patterns for Windows SolidWorks compatibility
- Template compilation with proper error recovery
- API compatibility for different SolidWorks versions

## [2.1.0] - 2025-01-11

### Added
- **Massive VBA Generation Expansion** - Added 5 new comprehensive VBA generation modules
- **Part Modeling VBA Tools** - Reference geometry, advanced features (sweep, loft, boundary), patterns, sheet metal, surface modeling
- **Assembly Automation VBA** - Complete mate types, component management, interference analysis, configuration management
- **Drawing Automation VBA** - View creation, dimensioning, annotations, tables, sheet format management
- **File Management & PDM VBA** - Batch operations, custom properties, PDM vault operations, design tables
- **Advanced Features VBA** - Configurations, equations, simulation setup, API automation, error handling

### Improved
- Fixed TypeScript compilation errors for better CI/CD stability
- Added proper type definitions for dotenv
- Corrected template string interpolation in VBA code generation
- Enhanced error handling in VBA generation

### Technical
- Added 3,300+ lines of sophisticated VBA generation code
- Modular architecture with domain-specific modules
- Full TypeScript support with Zod validation
- Comprehensive error handling and logging capabilities

## [2.0.1] - 2025-01-11

### Fixed
- Repository URLs corrected to GitHub repo
- Package-lock.json added for CI/CD
- ESLint errors resolved

## [2.0.0] - 2025-01-11

### Added
- Complete architecture rewrite with enterprise features
- Macro recording and playback system
- SQL integration for design tables
- PDM vault management
- Knowledge base with ChromaDB integration
- State management system
- Cache management
- Advanced resource registry

## [1.0.0] - 2025-01-08

### Added
- Initial release of SolidWorks MCP Server
- Full SolidWorks API integration via COM
- VBA script generation from templates
- Support for modeling operations (create, modify, dimension control)
- Drawing automation tools
- Multi-format export capabilities (STEP, IGES, STL, PDF, DXF, DWG)
- Analysis tools (mass properties, interference, geometry checks)
- Batch processing capabilities
- Automatic Claude Desktop configuration
- Comprehensive TypeScript implementation
- Windows-native COM integration via winax

### Features
- 25+ MCP tools for SolidWorks automation
- Handlebars-based VBA template system
- Support for SolidWorks 2021-2025
- One-command npm installation
- Auto-configuration of Claude Desktop
- Type-safe TypeScript architecture

### Documentation
- Comprehensive README with examples
- Installation guide
- Contributing guidelines
- VBA template examples