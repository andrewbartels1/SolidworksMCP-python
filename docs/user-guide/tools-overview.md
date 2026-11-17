# Tools Overview

The SolidWorks MCP Server provides 139 specialized tools for CAD automation. This page is a navigation map: each card links to the family's catalog page, which lists every tool with its inputs and a sample call.

## Read this first

- Every tool has a support level, shown on the [progress page](../progress.md).
  Seven are `planned` (registered so the name is kept, but every call returns
  `not_supported`) and eight are `deprecated` (they work, but another tool
  replaces them; see [below](#deprecated-tools)).
- A tool's name starts with a verb that says what it does: `create_` makes a
  document or feature, `add_` adds to a sketch, drawing or body, `get_` and
  `list_` read, `set_` changes a value, `check_`, `verify_`, `measure_` and
  `compare_` check. The full list is in the
  [tool description standard](../agents/tool-description-standard.md#tool-names).
- The mock adapter stands in for SolidWorks in tests. Its results show that a
  call is wired up, not that the CAD result is right; check that on SolidWorks.

## What each tool needs from SolidWorks

Any licence that runs SolidWorks is enough, Makers included: no tool calls an
add-in (Simulation, PDM, Routing, PhotoView) or a feature SolidWorks sells
only with Professional or Premium. Every live check ran on SOLIDWORKS
Professional for Makers 2026; Standard itself hasn't been run yet.

Each tool's `needs:` tag says what it needs. All but the 20 below need
SolidWorks running (`needs:running`).

### Needs nothing

These work with no SolidWorks on the machine (`needs:nothing`):
`generate_vba_code`, `generate_vba_extrusion`, `generate_vba_revolve`,
`generate_vba_assembly_insert`, `generate_vba_drawing_views`,
`generate_vba_batch_export`, `generate_vba_part_modeling`,
`generate_vba_assembly_mates`, `generate_vba_drawing_dimensions`,
`generate_vba_file_operations`, `generate_vba_macro_recorder`,
`compare_templates`, `compare_drawing_versions`, `reset_circuit_breaker`.

### Needs SolidWorks installed, not running

These read SolidWorks' installed files and never start it
(`needs:installed`): `discover_solidworks_docs`,
`search_solidworks_api_help`, `lookup_api_method`, `lookup_api_interface`,
`find_related_api_members`, `list_hole_sizes`.

## Tool Categories

<div class="grid cards" markdown>

- :material-cube-outline:{ .lg .middle } **Modeling Tools**

    ---

    Parts, assemblies and drawings: extrusions, revolves, sweeps, lofts, cuts, Hole Wizard holes, cosmetic threads, shells, drafts, ribs, fillets, chamfers, linear and circular patterns, reference geometry, mates, dimensions and the feature tree.

    [**42 tools available** :octicons-arrow-right-24:](tool-catalog/modeling.md)

- :material-pencil:{ .lg .middle } **Sketching Tools**

    ---

    Sketches on a plane or a flat face: lines, arcs, circles, rectangles, polygons, splines, relations, dimensions, offsets, mirrors, patterns and edges converted from the model.

    [**19 tools available** :octicons-arrow-right-24:](tool-catalog/sketching.md)

- :material-technical-draw:{ .lg .middle } **Drawing Tools**

    ---

    Drawings from a model: views, notes and centre marks. Section and detail views, dimensions and the title block are planned.

    [**13 tools available** :octicons-arrow-right-24:](tool-catalog/drawing.md)

- :material-file-cog:{ .lg .middle } **Drawing Automation**

    ---

    Model dimensions laid out without overlaps, datum tags, tolerances, BOM tables, sheet scale and complete drawing packages.

    [**7 tools available** :octicons-arrow-right-24:](tool-catalog/drawing-automation.md)

- :material-magnify:{ .lg .middle } **Drawing Analysis**

    ---

    Compare two versions of a drawing file.

    [**1 tool available** :octicons-arrow-right-24:](tool-catalog/drawing-analysis.md)

- :material-database:{ .lg .middle } **Engineering Data**

    ---

    Model dimensions by name, measurements, materials, custom properties and sheet-metal flat patterns.

    [**8 tools available** :octicons-arrow-right-24:](tool-catalog/engineering-data.md)

- :material-chart-line:{ .lg .middle } **Analysis Tools**

    ---

    Check a build against expected values, mass properties and interference.

    [**4 tools available** :octicons-arrow-right-24:](tool-catalog/analysis.md)

- :material-export:{ .lg .middle } **Export Tools**

    ---

    STEP, IGES, STL, PDF, DWG and images.

    [**6 tools available** :octicons-arrow-right-24:](tool-catalog/export.md)

- :material-folder-open:{ .lg .middle } **File Management**

    ---

    Open, save, switch and inspect documents; the feature tree, configurations and the current selection; Pack and Go.

    [**20 tools available** :octicons-arrow-right-24:](tool-catalog/file-management.md)

- :material-code-braces:{ .lg .middle } **VBA Generation**

    ---

    VBA macro text for steps the tools don't cover, written but not run.

    [**10 tools available** :octicons-arrow-right-24:](tool-catalog/vba-generation.md)

- :material-cog-play:{ .lg .middle } **Automation**

    ---

    A VBA macro skeleton for a described task.

    [**1 tool available** :octicons-arrow-right-24:](tool-catalog/automation.md)

- :material-record:{ .lg .middle } **Macro Recording**

    ---

    Run a binary SolidWorks macro (`.swp`).

    [**1 tool available** :octicons-arrow-right-24:](tool-catalog/macro-recording.md)

- :material-file-document:{ .lg .middle } **Template Management**

    ---

    Compare two template files.

    [**1 tool available** :octicons-arrow-right-24:](tool-catalog/template-management.md)

- :material-book-search:{ .lg .middle } **Docs Discovery**

    ---

    Look up SolidWorks API interfaces and members in the installed type library.

    [**5 tools available** :octicons-arrow-right-24:](tool-catalog/docs-discovery.md)

- :material-server:{ .lg .middle } **Server Admin**

    ---

    Reset the circuit breaker after a fault is fixed.

    [**1 tool available** :octicons-arrow-right-24:](../progress.md)

</div>

**Total: 139 Tools**

## Deprecated tools

These still work, and their results carry a `warning` naming the
replacement. They are removed in 3.0.0.

| Deprecated | Use instead |
| --- | --- |
| `load_part`, `load_assembly` | `open_model` |
| `save_part`, `save_assembly` | `save_file` (`pack_and_go_assembly` to copy an assembly with its parts) |
| `calculate_mass_properties` | `get_mass_properties` |
| `get_file_properties` | `get_model_info` |
| `add_drawing_view` | `create_drawing_view` |
| `sketch_tutorial_simple_hole` | the sketching and feature tools |
