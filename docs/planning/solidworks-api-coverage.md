# SolidWorks API Coverage Map

**Last updated:** 2026-06-13  
**Reference:** SolidWorks 2026 API (SOLIDWORKS COM API via pywin32)  
**Purpose:** Planning reference for future tool development — maps every major SolidWorks API functional category against what this MCP server currently implements.

---

## Table of Contents

1. [Implemented Tools](#1-implemented-tools)
2. [SolidWorks API Coverage Map](#2-solidworks-api-coverage-map)
3. [Missing High-Priority Tools](#3-missing-high-priority-tools)
4. [Missing Medium/Low Priority Tools](#4-missing-mediumlow-priority-tools)
5. [Summary Table](#5-summary-table)

---

## 1. Implemented Tools

### Document / Model Lifecycle (`modeling.py`, `file_management.py`)

| Tool Name | What It Does | SW API Category |
|---|---|---|
| `open_model` | Opens any SW file (.sldprt/.sldasm/.slddrw) | ISldWorks / IModelDoc2 |
| `create_part` | Creates a new blank part document | ISldWorks::NewDocument |
| `create_assembly` | Creates a new blank assembly document | ISldWorks::NewDocument |
| `create_drawing` | Creates a new blank drawing document | ISldWorks::NewDocument |
| `close_model` | Closes the active document (optionally saving) | IModelDoc2::CloseDoc |
| `load_part` | Convenience wrapper: opens a .sldprt | ISldWorks::OpenDoc6 |
| `load_assembly` | Convenience wrapper: opens a .sldasm | ISldWorks::OpenDoc6 |
| `save_file` | Saves the active document in place | IModelDoc2::Save3 |
| `save_as` | Saves the active document to a new path/format | IModelDoc2::SaveAs4 |
| `save_part` | Type-safe save with path validation for parts | IModelDoc2::Save3 |
| `save_assembly` | Type-safe save with path validation + reference copy | IModelDoc2::Save3 / GetDependencies2 |
| `get_file_properties` | Returns file metadata (simulated) | IModelDoc2::CustomPropertyManager |
| `get_model_info` | Compact model context summary (type, config, feature count) | IModelDoc2 introspection |
| `pack_and_go_assembly` | Copies assembly + all referenced parts to a new folder | IModelDocExtension::GetPackAndGo / SavePackAndGo |

### Feature Tree / Configurations (`file_management.py`)

| Tool Name | What It Does | SW API Category |
|---|---|---|
| `list_features` | Lists all feature-tree entries | IModelDoc2::FirstFeature / GetNextFeature |
| `classify_feature_tree` | Classifies model family (solid, sheet metal, VBA, assembly, drawing) | Internal classifier |
| `list_configurations` | Lists configuration names | IModelDoc2::GetConfigurationNames |
| `manage_file_properties` | Read/update/copy/move/delete file properties | IModelDoc2::CustomPropertyManager |
| `convert_file_format` | Convert file to another format via export | IModelDoc2::SaveAs4 |
| `batch_file_operations` | Bulk file lifecycle operations | Filesystem |
| `batch_export` | Batch-converts directories of SW files | ISldWorks / IModelDoc2::SaveAs4 |

### Sketching (`sketching.py`)

| Tool Name | What It Does | SW API Category |
|---|---|---|
| `create_sketch` | Creates a new sketch on a named reference plane | ISketchManager::InsertSketch |
| `exit_sketch` | Exits sketch editing mode | ISketchManager::InsertSketch (exit) |
| `check_sketch_fully_defined` | Reports under/fully/over-defined status | ISketch::IsFullyDefined |
| `add_line` | Adds a line segment | ISketchManager::CreateLine |
| `add_circle` | Adds a circle | ISketchManager::CreateCircle |
| `add_rectangle` | Adds a 2-corner rectangle (4 lines) | ISketchManager::CreateCornerRectangle |
| `add_arc` | Adds a center-point arc | ISketchManager::CreateArc |
| `add_spline` | Adds a spline through control points | ISketchManager::CreateSpline |
| `add_centerline` | Adds a construction/centerline | ISketchManager::CreateLine (construction) |
| `add_polygon` | Adds a regular N-sided polygon | ISketchManager::CreatePolygon |
| `add_ellipse` | Adds an ellipse | ISketchManager::CreateEllipse |
| `add_sketch_constraint` | Adds a geometric relation (parallel, tangent, etc.) | ISketchRelationManager::AddRelation |
| `add_sketch_dimension` | Adds a dimensional constraint | IModelDocExtension::AddSmartDimension2 |
| `sketch_linear_pattern` | Linear step-and-repeat of sketch entities | ISketchManager::CreateLinearSketchStepAndRepeat |
| `sketch_circular_pattern` | Circular step-and-repeat of sketch entities | ISketchManager::CreateCircularSketchStepAndRepeat |
| `sketch_mirror` | Mirrors entities about a centerline | ISketchManager::SketchMirror |
| `sketch_offset` | Offsets sketch entities by a distance | ISketchManager::SketchOffset4 |
| `sketch_tutorial_simple_hole` | Tutorial: full hole sketch workflow | Composed from above |
| `tutorial_simple_hole` | Guided tutorial: sketch+cut workflow | Composed from above |

### Feature Modeling — Boss/Cut/Form (`modeling.py`, `adapters/solidworks/features.py`)

| Tool Name | What It Does | SW API Category |
|---|---|---|
| `create_extrusion` | Boss-extrude from active sketch | IFeatureManager::FeatureExtrusion3 |
| `create_cut_extrude` | Cut-extrude from active sketch | IFeatureManager::FeatureCut4 |
| `create_revolve` | Revolve boss around centerline axis | IFeatureManager::FeatureRevolve2 |
| `create_sweep` | Sweep profile along a path sketch | IFeatureManager::InsertProtrusionSwept4 |
| `create_loft` | Loft solid between ≥2 profile sketches | IFeatureManager::InsertProtrusionBlend2 |
| `add_fillet` | Constant-radius fillet on named edges | IModelDoc2::FeatureFillet3 / IFeatureManager::FeatureFillet3 |
| `add_chamfer` | Equal-distance chamfer on named edges (adapter only, no MCP tool yet) | IFeatureManager::InsertFeatureChamfer |
| `get_dimension` | Reads a named dimension value | IModelDoc2::Parameter |
| `set_dimension` | Sets a named dimension and rebuilds | IModelDoc2::Parameter / ForceRebuild3 |

### Export (`export.py`)

| Tool Name | What It Does | SW API Category |
|---|---|---|
| `export_step` | STEP export (AP214/AP203) | IModelDoc2::SaveAs4 |
| `export_iges` | IGES export | IModelDoc2::SaveAs4 |
| `export_stl` | STL export (binary/ASCII) | IModelDoc2::SaveAs4 |
| `export_pdf` | PDF export from drawing/part | IModelDoc2::SaveAs4 |
| `export_dwg` | DWG export from drawing | IModelDoc2::SaveAs4 |
| `export_image` | JPG/PNG/BMP image capture | IModelDoc2::SaveBitmapWithVariable |
| `batch_export` | Directory-level multi-format export | Composed from above |

### Analysis (`analysis.py`)

| Tool Name | What It Does | SW API Category |
|---|---|---|
| `calculate_mass_properties` | Volume, surface area, mass, CoM, MoI | IMassProperty |
| `get_mass_properties` | Alias for calculate_mass_properties | IMassProperty |
| `check_interference` | Assembly interference detection | IInterferenceDetectionMgr |
| `analyze_geometry` | Curvature/draft/thickness analysis (simulated) | ISurface / IGeometryManager |
| `get_material_properties` | Material properties (simulated) | IPartDoc::GetMaterialPropertyName2 |

### Drawing (`drawing.py`, `drawing_analysis.py`)

| Tool Name | What It Does | SW API Category |
|---|---|---|
| `create_drawing_view` | Creates a model view in a drawing (simulated) | IDrawingDoc::CreateDrawViewFromModelView3 |
| `add_dimension` | Adds a dimension in a drawing (simulated) | IModelDocExtension::AddSmartDimension2 |
| `add_note` | Adds a text note (simulated) | IAnnotationView::InsertNote |
| `create_section_view` | Creates a section view (simulated) | IDrawingDoc::CreateSectionView5 |
| `create_detail_view` | Creates a detail view (simulated) | IDrawingDoc::CreateDetailViewAt4 |
| `update_sheet_format` | Applies a sheet format template (simulated) | ISheet::SetSheetInfo2 |
| `auto_dimension_view` | Auto-dimensions a view (simulated) | IModelDocExtension::AddSmartDimension2 |
| `check_drawing_standards` | Validates against drafting standards (simulated) | Internal |
| `create_technical_drawing` | Full drawing-from-model workflow | IDrawingDoc |
| `add_drawing_view` | Add/update/delete a drawing view | IDrawingDoc |
| `add_annotation` | Add annotation (note, balloon, symbol) | IAnnotationView |
| `update_title_block` | Update title block fields | ISheet / INote |
| `analyze_drawing_comprehensive` | Full quality analysis of a drawing (simulated) | IDrawingDoc inspection |
| `analyze_drawing_dimensions` | Dimension consistency analysis (simulated) | IDisplayDimension |
| `analyze_drawing_annotations` | Annotation quality analysis (simulated) | INote / IAnnotation |
| `check_drawing_compliance` | Standards compliance check (simulated) | Internal |
| `analyze_drawing_views` | Drawing view analysis (simulated) | IView |
| `generate_drawing_report` | Comprehensive quality report (simulated) | Internal |
| `compare_drawing_versions` | Compares two drawing revisions (simulated) | Internal |
| `validate_drawing_completeness` | Manufacturing readiness check (simulated) | Internal |

### Automation (`automation.py`)

| Tool Name | What It Does | SW API Category |
|---|---|---|
| `generate_vba_code` | Generates template VBA code for an operation | Internal template |
| `automation_start_macro_recording` | Starts SolidWorks macro recording (simulated) | ISldWorks::RunMacro2 |
| `automation_stop_macro_recording` | Stops macro recording (simulated) | ISldWorks::RunMacro2 |
| `batch_process_files` | Batch rebuild/export across a directory (simulated) | ISldWorks / IModelDoc2 |
| `manage_design_table` | Create/update Excel-driven design tables (simulated) | IDesignTable |
| `execute_workflow` | Sequential/parallel tool pipeline (simulated) | Internal |
| `create_template` | Creates a blank document template file (simulated) | ISldWorks::NewDocument |
| `optimize_performance` | Suggests/applies SW performance settings (simulated) | ISldWorks::SetUserPreferenceIntegerValue |

### Miscellaneous

| Tool Name | What It Does | SW API Category |
|---|---|---|
| `vba_generation.*` | Advanced VBA generation helpers | Internal |
| `docs_discovery.*` | SW API documentation search | Web/filesystem |
| `template_management.*` | Template extract/apply/batch/compare | IModelDoc2 / CustomPropertyManager |
| `macro_recording.*` | Dedicated macro recording module | ISldWorks::RunMacro2 |

**Total implemented MCP tools: ~75**  
**Backed by real COM calls: ~40** (the remainder return simulated/placeholder data)

---

## 2. SolidWorks API Coverage Map

The SW API is organized around the major interfaces exposed by the COM type library. Categories below map to the official SolidWorks API functional hierarchy.

---

### 2.1 Application-Level API (`ISldWorks`)

Covers top-level application control: document management, add-in registration, user-preference settings, macro execution, and application events.

| Operation | Status | Tool / Notes |
|---|---|---|
| Open document (`OpenDoc6`) | Implemented | `open_model`, `load_part`, `load_assembly` |
| Create new document (`NewDocument`) | Implemented | `create_part`, `create_assembly`, `create_drawing` |
| Close document (`CloseDoc`) | Implemented | `close_model` |
| Get active document (`ActiveDoc`) | Implemented | Internal — used by all adapter ops |
| List open documents (`GetDocuments`) | **Missing** (Medium) | Needed for multi-doc workflows |
| Activate a specific document | **Missing** (Medium) | Needed for multi-doc workflows |
| Run a VBA macro (`RunMacro2`) | Simulated | `automation_start_macro_recording` |
| Get/set user preferences (`SetUserPreferenceIntegerValue`) | **Missing** (Low) | `optimize_performance` stubs this |
| SolidWorks version info (`RevisionNumber`) | Implemented | Internal version detection in features.py |
| Add-in management | **Missing** (Low) | `GetAddInObject`, etc. |
| Application events (document open/close callbacks) | **Missing** (Low) | Event sink registration |
| Frame/window handle | **Missing** (Low) | UI manipulation |

---

### 2.2 Document API (`IModelDoc2`) — Core

Covers operations on the active document regardless of type (part/assembly/drawing): rebuild, properties, selection, dimensions, and configurations.

| Operation | Status | Tool / Notes |
|---|---|---|
| `Save3` / `SaveAs4` | Implemented | `save_file`, `save_as`, `save_part`, `save_assembly` |
| `ForceRebuild3` | Implemented | Internal — called before SelectByID2 |
| `Parameter` (read dimension) | Implemented | `get_dimension` |
| `Parameter.SystemValue = x` (write dimension) | Implemented | `set_dimension` |
| `FirstFeature` / `GetNextFeature` | Implemented | `list_features`, internal tree walks |
| `FeatureByName` | Implemented | Internal — sweep/loft/selection |
| `GetPathName` | Implemented | Internal — pack-and-go reference resolution |
| `GetTitle` | Implemented | Internal — model info |
| `GetDependencies2` | Implemented | `save_assembly` with `include_references=True` |
| `GetConfigurationNames` | Implemented | `list_configurations` |
| `ActiveConfiguration` | **Missing** (High) | Switch/get active configuration |
| `ShowConfiguration2` | **Missing** (High) | Activate a configuration by name |
| `AddConfiguration3` | **Missing** (Medium) | Create a new configuration |
| `CopyConfiguration` | **Missing** (Low) | Duplicate a configuration |
| `DeleteConfiguration2` | **Missing** (Low) | Remove a configuration |
| `GetAnnotations` (in 3D) | **Missing** (Medium) | 3D annotation / model-based definition |
| `InsertNote` (3D) | **Missing** (Medium) | 3D annotation notes |
| `CustomPropertyManager.Get6/Set` | **Missing** (High) | Read/write custom file properties (real) |
| `Extension.CustomPropertyManager` | **Missing** (High) | Per-configuration custom properties |
| `SketchManager` (enter sketch) | Implemented | `create_sketch` |
| `ClearSelection2` | Implemented | Internal — used before multi-edge operations |
| `FeatureFillet3` | Implemented | `add_fillet` |
| `FeatureChamfer` | Implemented | `add_chamfer` (adapter only, no MCP tool) |

---

### 2.3 Part API (`IPartDoc`)

Extends `IModelDoc2` for parts: body operations, material assignment, sheet metal.

| Operation | Status | Tool / Notes |
|---|---|---|
| `GetBodies2` — list solid bodies | **Missing** (High) | Multi-body part inspection |
| `GetMaterialPropertyName2` | Simulated | `get_material_properties` returns hard-coded data |
| `SetMaterialPropertyName2` | **Missing** (High) | Assign material by name |
| `GetSurfaceBodies` | **Missing** (Medium) | Surface model inspection |
| Sheet metal operations (`ISheetMetalFeatureData`) | **Missing** (High) | Flat pattern, bend table, k-factor |
| `InsertBend` / `InsertBaseFlange` | **Missing** (High) | Sheet metal feature creation |
| `FlattenBends` | **Missing** (High) | Unfold flat pattern |
| Weldment operations | **Missing** (Low) | Structural member insertion |
| `GetFeatureManagerDesignTree` | Implemented (indirectly) | `list_features` |
| Multi-body: `InsertCombineFeature` | **Missing** (Medium) | Combine / subtract bodies |
| `InsertShell` | **Missing** (Medium) | Shell feature |
| `InsertRib` | **Missing** (Low) | Rib feature |
| `InsertDome` | **Missing** (Low) | Dome feature |
| `InsertSplit` | **Missing** (Low) | Split body |

---

### 2.4 Assembly API (`IAssemblyDoc`)

Extends `IModelDoc2` for assemblies: component insertion, mating, explode views, BOM.

| Operation | Status | Tool / Notes |
|---|---|---|
| `AddComponent5` — insert component | **Missing** (High) | Insert parts into an assembly |
| `GetComponents` — list components | **Missing** (High) | Enumerate assembly components |
| `GetComponentByName` | **Missing** (High) | Locate a specific component |
| `AddMate5` — add mate constraint | **Missing** (High) | Coincident, concentric, distance mates |
| `GetMates` — list mates | **Missing** (Medium) | Enumerate existing mates |
| `DeleteMate` | **Missing** (Medium) | Remove a mate |
| `CheckInterferences` | Simulated | `check_interference` (real adapter path present) |
| `ExplodeView` | **Missing** (Medium) | Create explode view |
| `UnExplodeView` | **Missing** (Low) | Collapse explode |
| `AutoExplode` | **Missing** (Low) | Auto-generate explode steps |
| BOM management (`IBomTable`) | **Missing** (Medium) | Insert/update BOM table |
| Pattern component (`InsertLinearComponentPattern`) | **Missing** (Low) | Linear component array |
| Pattern component (`InsertCircularComponentPattern`) | **Missing** (Low) | Circular component array |
| Mirror component (`InsertMirrorComponent`) | **Missing** (Low) | Mirror component |
| Smart mates | **Missing** (Low) | Smart-mate via drag |
| Simulation-ready assembly check | **Missing** (Low) | Pre-simulation validation |

---

### 2.5 Drawing API (`IDrawingDoc`)

Extends `IModelDoc2` for drawings: sheets, views, annotations, BOM tables, revision tables.

| Operation | Status | Tool / Notes |
|---|---|---|
| `CreateDrawViewFromModelView3` | Simulated | `create_drawing_view` (no real COM yet) |
| `CreateSectionView5` | Simulated | `create_section_view` |
| `CreateDetailViewAt4` | Simulated | `create_detail_view` |
| `CreateAuxiliaryViewAt` | **Missing** (High) | Auxiliary view from angled edge |
| `CreateProjectionView` | **Missing** (High) | Projected view from existing view |
| `ActivateView` | **Missing** (Medium) | Focus a drawing view for editing |
| Sheet management (`ISheet::SetSheetInfo2`) | Simulated | `update_sheet_format` |
| Add/remove sheets | **Missing** (Medium) | Multi-sheet drawings |
| Rename/reorder sheets | **Missing** (Low) | Sheet lifecycle |
| `AddBomTable4` — insert BOM table | **Missing** (High) | Bill of materials |
| Revision table | **Missing** (Medium) | Drawing revision history |
| General table | **Missing** (Low) | Custom tables |
| `IView::GetOutline` | **Missing** (Medium) | View bounding box for layout |
| `IView::ScaleX` / `ScaleY` | **Missing** (Medium) | Per-view scale control |
| Move/align views | **Missing** (Medium) | View layout management |
| Break view | **Missing** (Low) | Broken-out section |
| Crop view | **Missing** (Low) | Cropped view boundary |
| Smart dimension in drawing | Simulated | `add_dimension` (no real COM yet) |
| Ordinate dimension | **Missing** (Medium) | Ordinate/baseline dimension chains |
| Geometric tolerance (FCF) | **Missing** (Medium) | Feature control frames |
| Surface finish symbol | **Missing** (Medium) | ISO/ANSI surface finish callouts |
| Weld symbol | **Missing** (Low) | Weld annotation |
| Datum target | **Missing** (Low) | GD&T datum targets |
| Balloon annotation | **Missing** (Medium) | Assembly balloon callouts |
| Center mark / centerline | **Missing** (Medium) | Automatic center marks |
| Hole callout | **Missing** (High) | Automatic hole note generation |
| Note (real) | Simulated | `add_note` (no real COM yet) |
| Layer management | **Missing** (Low) | Drawing layers |
| Print/plot drawing | **Missing** (Medium) | Print to paper/PDF via API |
| `IDrawingDoc::RebuildAndSave` | **Missing** (Low) | Rebuild drawing views |

---

### 2.6 Sketch API (`ISketchManager` / `ISketch`)

| Operation | Status | Tool / Notes |
|---|---|---|
| `InsertSketch` (enter/exit) | Implemented | `create_sketch`, `exit_sketch` |
| `CreateLine` | Implemented | `add_line` |
| `CreateCircle` | Implemented | `add_circle` |
| `CreateCornerRectangle` | Implemented | `add_rectangle` |
| `CreateArc` (center-point) | Implemented | `add_arc` |
| `CreateSpline` | Implemented | `add_spline` |
| `CreateEllipse` | Implemented | `add_ellipse` |
| `CreatePolygon` | Implemented | `add_polygon` |
| `SketchMirror` | Implemented | `sketch_mirror` |
| `SketchOffset4` | Implemented | `sketch_offset` |
| `CreateLinearSketchStepAndRepeat` | Implemented | `sketch_linear_pattern` |
| `CreateCircularSketchStepAndRepeat` | Implemented | `sketch_circular_pattern` |
| `AddRelation` (via ISketchRelationManager) | Implemented | `add_sketch_constraint` |
| `AddSmartDimension2` | Implemented | `add_sketch_dimension` |
| Trim entities (`SketchTrim5`) | **Missing** (High) | Trim/extend sketch geometry |
| Split entities (`SketchSplit`) | **Missing** (Medium) | Split a sketch entity at a point |
| Sketch text (`InsertSketchText`) | **Missing** (Medium) | Emboss/engrave text via sketch |
| Convert entities (`SketchConvertEntities`) | **Missing** (High) | Project model edges into sketch |
| Intersection curve | **Missing** (Medium) | Intersect surfaces/planes with sketch |
| 3D sketch | **Missing** (Medium) | `Insert3DSketch` — curves in 3D space |
| `ISketch::IsFullyDefined` | Implemented | `check_sketch_fully_defined` |
| `SketchFillet` | **Missing** (Medium) | Sketch-level fillet (rounds corner) |
| `SketchChamfer` | **Missing** (Low) | Sketch-level chamfer |
| Dynamic mirror (live symmetry) | **Missing** (Low) | `ISketchManager::InsertSketchMirror` |
| Sketch picture / texture | **Missing** (Low) | Import image as sketch reference |
| 3-point arc | **Missing** (Low) | `CreateArc` 3-point variant |
| Parabolic / conic arc | **Missing** (Low) | Conic sections |

---

### 2.7 Feature Manager API (`IFeatureManager`)

| Operation | Status | Tool / Notes |
|---|---|---|
| `FeatureExtrusion3` / `FeatureExtrusion2` | Implemented | `create_extrusion` |
| `FeatureCut4` / `FeatureCut3` | Implemented | `create_cut_extrude` |
| `FeatureRevolve2` | Implemented | `create_revolve` |
| `InsertProtrusionSwept4` | Implemented | `create_sweep` |
| `InsertProtrusionBlend2` (loft) | Implemented | `create_loft` |
| `FeatureFillet3` | Implemented | `add_fillet` |
| `InsertFeatureChamfer` | Implemented (adapter) | `add_chamfer` — adapter has it, no MCP tool |
| `InsertShell` | **Missing** (High) | Shell out a solid |
| `InsertRib` | **Missing** (Medium) | Rib feature |
| Linear pattern (`FeatureLinearPattern3`) | **Missing** (High) | Array of features/bodies |
| Circular pattern (`FeatureCircularPattern3`) | **Missing** (High) | Rotational array of features |
| Mirror feature (`InsertMirrorFeature2`) | **Missing** (High) | Mirror features about a plane |
| Hole Wizard (`HoleWizard5`) | **Missing** (High) | Parametric holes per ANSI/ISO standards |
| Draft feature (`InsertDraftXpert`) | **Missing** (Medium) | Parting line draft |
| `InsertDome` | **Missing** (Low) | Dome feature |
| `InsertSplit` | **Missing** (Low) | Split body feature |
| `InsertScale` | **Missing** (Low) | Scale body |
| `InsertThicken` | **Missing** (Medium) | Thicken a surface |
| Wrap feature (`InsertWrap2`) | **Missing** (Low) | Wrap sketch onto surface |
| Flex feature | **Missing** (Low) | Flex/deform a body |
| `InsertCutSurface` | **Missing** (Low) | Surface cut |
| Cut-revolve | **Missing** (Medium) | Revolve cut (complement to `create_revolve`) |
| Cut-sweep | **Missing** (Medium) | Sweep cut |
| Cut-loft | **Missing** (Medium) | Loft cut |
| `InsertProtrusionBlend2` cut-variant | **Missing** (Medium) | Loft cut |
| `InsertBoundaryBoss` | **Missing** (Low) | Boundary feature |
| `InsertDeformSurface` | **Missing** (Low) | Deform surface |
| `InsertFreeform` | **Missing** (Low) | Freeform surface push/pull |
| `InsertMoldCavity` | **Missing** (Low) | Mold cavity |

---

### 2.8 Configuration API (`IConfiguration` / `IConfigurationManager`)

| Operation | Status | Tool / Notes |
|---|---|---|
| `GetConfigurationNames` | Implemented | `list_configurations` |
| `ShowConfiguration2` (activate) | **Missing** (High) | Switch active configuration |
| `AddConfiguration3` (create) | **Missing** (Medium) | New configuration |
| `CopyConfiguration` | **Missing** (Low) | Copy config with all properties |
| `DeleteConfiguration2` | **Missing** (Low) | Remove a config |
| `IConfiguration.Name` | **Missing** (Medium) | Read config name / properties |
| `IConfiguration.Comment` | **Missing** (Low) | Read config description |
| Design table (`IDesignTable`) | Simulated | `manage_design_table` (no real COM) |
| `GetDesignTable` | **Missing** (Medium) | Read existing design table |
| `InsertFamilyTableMate` | **Missing** (Low) | Mate config in family table |
| Explode states per config | **Missing** (Low) | Per-config explode |
| Display states | **Missing** (Low) | Appearance per config |
| Derived configurations | **Missing** (Low) | Linked child configs |

---

### 2.9 Selection API (`IModelDocExtension::SelectByID2` / `ISelectionMgr`)

| Operation | Status | Tool / Notes |
|---|---|---|
| `SelectByID2` (by entity name + type) | Implemented | Internal — used by fillet, chamfer, cut |
| `SelectByID2` (by coordinate) | Implemented | Internal — coordinate-based edge selection |
| `Select2` (via `IFeature`) | Implemented | Internal — sweep/loft profile selection |
| `ClearSelection2` | Implemented | Internal |
| `ForceRebuild3` (pre-selection rebuild) | Implemented | Internal |
| `GetSelectedObjectCount2` | **Missing** (Medium) | Query selection state |
| `GetSelectedObject6` | **Missing** (Medium) | Inspect what is selected |
| `ISelectionMgr::GetSelectedObjectsComponent3` | **Missing** (Low) | Assembly component from selection |
| Selection filters | **Missing** (Low) | Filter selection to faces/edges/vertices |

---

### 2.10 Equations / Global Variables (`IEquationMgr`)

| Operation | Status | Tool / Notes |
|---|---|---|
| Read equation value | Partially (via `get_dimension`) | Only named dimensions; not arbitrary equations |
| `GetEquationCount` | **Missing** (High) | Number of equations in model |
| `GetEquation` | **Missing** (High) | Read a specific equation string |
| `SetEquation` | **Missing** (High) | Create/update an equation |
| `DeleteEquation` | **Missing** (Medium) | Remove an equation |
| Global variables | **Missing** (High) | `$MassX` type variables driving multiple dims |
| Linked values | **Missing** (Medium) | Read linked dimension values |

---

### 2.11 Mass Properties (`IMassProperty`)

| Operation | Status | Tool / Notes |
|---|---|---|
| Volume | Implemented | `calculate_mass_properties` |
| Surface area | Implemented | `calculate_mass_properties` |
| Mass | Implemented | `calculate_mass_properties` |
| Center of mass | Implemented | `calculate_mass_properties` |
| Moments of inertia (Ixx, Iyy, Izz, Ixy, Ixz, Iyz) | Implemented | `calculate_mass_properties` |
| Principal axes | Implemented | `calculate_mass_properties` |
| Per-body mass props (multi-body) | **Missing** (Medium) | Multi-body breakdowns |
| Per-component mass props (assembly) | **Missing** (Medium) | Assembly component mass rollup |
| Override mass / center of mass | **Missing** (Low) | Custom mass overrides |

---

### 2.12 Geometry / Topology API (`IFace2`, `IEdge`, `IVertex`, `IBody2`)

| Operation | Status | Tool / Notes |
|---|---|---|
| `GetFaces` | **Missing** (High) | Enumerate faces on a body |
| `IFace2::GetArea` | **Missing** (High) | Face area (for selection, analysis) |
| `IFace2::Normal` | **Missing** (Medium) | Face normal vector |
| `IEdge::GetCurve` | **Missing** (Medium) | Underlying curve of an edge |
| `IEdge::GetLength` | **Missing** (Medium) | Edge length |
| `IVertex::GetPoint` | **Missing** (Medium) | Vertex 3D coordinates |
| `IBody2::GetMassProperties` | **Missing** (Medium) | Per-body mass properties |
| Bounding box (`GetBox`) | **Missing** (High) | Model bounding box for packaging |
| Ray intersection | **Missing** (Low) | Raycast for selection helpers |
| Sheet metal flat pattern geometry | **Missing** (High) | Flat pattern faces/bends for DXF export |

---

### 2.13 Materials API (`IPartDoc` / `IMaterial`)

| Operation | Status | Tool / Notes |
|---|---|---|
| `GetMaterialPropertyName2` | Simulated | `get_material_properties` returns hard-coded data |
| `SetMaterialPropertyName2` | **Missing** (High) | Assign material to a body |
| Material library (`ISwAppExt::GetMaterialDatabaseFileNames`) | **Missing** (Medium) | List available materials |
| Custom material creation | **Missing** (Low) | Define new material in library |
| Material appearance / color | **Missing** (Low) | Visual material properties |
| `IPartDoc::DeleteMaterialProperty` | **Missing** (Low) | Remove material assignment |

---

### 2.14 Reference Geometry (`IRefPlane`, `IRefAxis`, `IRefPoint`)

| Operation | Status | Tool / Notes |
|---|---|---|
| Select named plane for sketch | Implemented | `create_sketch` resolves "Top/Front/Right" |
| `InsertRefSurface` (reference plane) | **Missing** (High) | Create custom reference plane |
| `InsertRefAxis` | **Missing** (Medium) | Create a reference axis |
| `InsertRefPoint` | **Missing** (Low) | Create a reference point |
| Mate references | **Missing** (Low) | Persistent mate references on a model |
| Bounding box reference | **Missing** (Low) | Auto bounding box reference geometry |

---

### 2.15 Appearances / Display (`IDisplayStateMgr`, `IAppearanceSetting`)

| Operation | Status | Tool / Notes |
|---|---|---|
| Set body color | **Missing** (Medium) | Per-body/face appearance |
| Assign material appearance | **Missing** (Low) | Visual texture/finish |
| Display states | **Missing** (Low) | Per-configuration visual states |
| `IModelDoc2::ViewZoomtofit2` | **Missing** (Low) | Zoom-to-fit for screenshots |
| Render with PhotoView 360 | **Missing** (Low) | High-fidelity render |
| Section view (3D) | **Missing** (Low) | In-session clipping planes |

---

### 2.16 File Format Import/Export (Extended)

| Operation | Status | Tool / Notes |
|---|---|---|
| STEP export | Implemented | `export_step` |
| IGES export | Implemented | `export_iges` |
| STL export | Implemented | `export_stl` |
| PDF export | Implemented | `export_pdf` |
| DWG/DXF export | Implemented | `export_dwg` |
| Image export (JPG/PNG) | Implemented | `export_image` |
| 3MF export | **Missing** (Medium) | Additive manufacturing format |
| OBJ export | **Missing** (Low) | Mesh exchange format |
| ACIS (SAT) export | **Missing** (Low) | ACIS solid exchange |
| Parasolid export | **Missing** (Low) | Parasolid kernel exchange |
| VRML export | **Missing** (Low) | Legacy 3D web format |
| AMF export | **Missing** (Low) | Additive manufacturing format v2 |
| DXF flat-pattern export | **Missing** (High) | Sheet metal flat pattern for laser cutting |
| eDrawings export | **Missing** (Low) | SW viewer format |
| Import STEP/IGES | **Missing** (Medium) | Open a neutral format file |
| Import DXF/DWG | **Missing** (Low) | Import 2D CAD geometry |

---

### 2.17 Pack and Go / References

| Operation | Status | Tool / Notes |
|---|---|---|
| `IModelDocExtension::GetPackAndGo` | Implemented | `pack_and_go_assembly` (native path) |
| `IPackAndGo::SavePackAndGo` | Implemented | `pack_and_go_assembly` |
| `IPackAndGo::SetSaveToName` | Implemented | Internal |
| `IPackAndGo::FlattenToSingleFolder` | Implemented | Internal |
| `GetDependencies2` (fallback) | Implemented | `save_assembly` include_references |
| Update file references (`ReplaceReferencedDocument`) | **Missing** (Medium) | Repath a reference |
| Find and repair broken references | **Missing** (Medium) | Reference repair workflow |
| `IModelDoc2::FileFindReferences` | **Missing** (Low) | List where-used |

---

### 2.18 Macros and VBA (`ISldWorks::RunMacro2`, `IVBAMacro`)

| Operation | Status | Tool / Notes |
|---|---|---|
| Generate VBA code (template) | Implemented | `generate_vba_code` |
| Run an existing VBA macro | **Missing** (High) | `RunMacro2(path, module, sub)` |
| Start/stop macro recording | Simulated | `automation_start_macro_recording` |
| Export/import macro | **Missing** (Low) | .swp file management |

---

### 2.19 Simulation / Analysis (SolidWorks Simulation / Flow)

> These require the SolidWorks Simulation and/or Flow Simulation add-in to be licensed and loaded.

| Operation | Status | Tool / Notes |
|---|---|---|
| FEA study creation | **Missing** (Low) | COSMOSWORKS/SW Simulation add-in |
| FEA mesh generation | **Missing** (Low) | SW Simulation |
| FEA result extraction | **Missing** (Low) | Stress, displacement results |
| Flow simulation | **Missing** (Low) | SW Flow Simulation add-in |
| Motion study | **Missing** (Low) | SW Motion add-in |
| Fatigue / design study | **Missing** (Low) | SW Simulation Premium |

---

## 3. Missing High-Priority Tools

These are the most impactful gaps — operations that a typical modeling workflow needs and that the current server cannot handle with real COM calls.

---

### 3.1 `add_chamfer` MCP Tool

**Why needed:** The adapter (`adapters/solidworks/features.py`) already implements `_add_chamfer_impl` using `IFeatureManager::InsertFeatureChamfer` but there is no corresponding MCP tool in `modeling.py`. Every add-fillet workflow also needs chamfer for sharp edge breaks.

**What to add:**
```python
# modeling.py — mirror AddFilletInput
class AddChamferInput(CompatInput):
    distance: float = Field(description="Chamfer distance in millimeters")
    edge_names: list[str] = Field(default_factory=list)
    
async def add_chamfer(input_data: AddChamferInput) -> dict[str, Any]:
    result = await adapter.add_chamfer(input_data.distance, input_data.edge_names)
    ...
```

---

### 3.2 Configuration Management Tools

**Why needed:** Almost all real SW parts have multiple configurations (material variants, size families). Without the ability to switch, create, and inspect configurations, the server cannot support parametric variant workflows.

**Tools to add:**
- `switch_configuration(name: str)` → `IModelDoc2::ShowConfiguration2`
- `get_active_configuration()` → `IModelDoc2::ConfigurationManager::ActiveConfiguration`
- `add_configuration(name: str, copy_from: str | None)` → `IModelDoc2::AddConfiguration3`
- `delete_configuration(name: str)` → `IModelDoc2::DeleteConfiguration2`

**Adapter method:** `pywin32_adapter.py` via the COM executor.

---

### 3.3 Custom Properties (Real Implementation)

**Why needed:** `get_file_properties()` returns hard-coded simulated data. Custom properties are used for BOM, revision tracking, and PLM integrations. This is one of the most-used SW API features in enterprise workflows.

**Tools to add:**
- `get_custom_properties(config_name: str | None)` → `IModelDoc2::Extension::CustomPropertyManager::Get6`
- `set_custom_property(name: str, value: str, config_name: str | None)` → `ICustomPropertyManager::Set3`
- `delete_custom_property(name: str, config_name: str | None)` → `ICustomPropertyManager::Delete2`

---

### 3.4 Material Assignment (Real Implementation)

**Why needed:** `get_material_properties()` is entirely simulated. Assigning the correct material drives mass properties, simulation, and BOM data. This is a basic modeling task.

**Tools to add:**
- `set_material(material_name: str, library: str | None)` → `IPartDoc::SetMaterialPropertyName2`
- `get_material()` → `IPartDoc::GetMaterialPropertyName2` (real call)
- `list_available_materials(library: str | None)` → filesystem scan of SW material DB

---

### 3.5 Feature Pattern Tools

**Why needed:** Linear/circular patterns are the most common operation for creating arrays of holes, bosses, or cuts. There is no pattern tool today.

**Tools to add:**
- `create_linear_pattern(feature_name: str, direction: str, spacing: float, count: int, direction2: str | None, spacing2: float | None, count2: int | None)` → `IFeatureManager::FeatureLinearPattern3`
- `create_circular_pattern(feature_name: str, axis: str, angle: float, count: int)` → `IFeatureManager::FeatureCircularPattern3`
- `mirror_feature(feature_name: str, mirror_plane: str)` → `IFeatureManager::InsertMirrorFeature2`

---

### 3.6 Hole Wizard Tool

**Why needed:** Hole Wizard creates parametric, standards-compliant holes (clearance holes, tapped holes, counterbores, countersinks) that appear correctly in BOMs and drawings. Raw cut-extrude cannot encode the fastener standard.

**Tools to add:**
- `create_hole_wizard(standard: str, type: str, size: str, depth: float | None, position_x: float, position_y: float, plane: str)` → `IFeatureManager::HoleWizard5`

---

### 3.7 Convert Entities (Sketch)

**Why needed:** "Convert Entities" projects existing model edges/faces into the active sketch. This is used in nearly every sketch-on-face workflow (e.g., pocket on a face that matches the face boundary). Without it, users must manually redraw geometry.

**Tools to add:**
- `sketch_convert_entities(entity_names: list[str])` → `ISketchManager::SketchConvertEntities`

---

### 3.8 Trim / Extend Entities (Sketch)

**Why needed:** After adding multiple intersecting sketch entities (circles, lines), you need to trim the unwanted portions. This is required for any complex profile (slots with rounded ends, keyways, etc.).

**Tools to add:**
- `sketch_trim(entity_name: str, trim_location_x: float, trim_location_y: float)` → `ISketchManager::SketchTrim5`

---

### 3.9 Run Existing Macro

**Why needed:** The `generate_vba_code` tool generates code but cannot execute it. Closing the loop by running a saved `.swp` macro file would unlock complex operations not directly supported by the MCP API surface.

**Tools to add:**
- `run_macro(macro_path: str, module_name: str, sub_name: str)` → `ISldWorks::RunMacro2`

---

### 3.10 Assembly Component Operations

**Why needed:** Creating assemblies currently only creates the assembly document; no components can be inserted or mated. This gap makes the assembly workflow unusable end-to-end.

**Tools to add:**
- `insert_component(part_path: str, position: list[float] | None)` → `IAssemblyDoc::AddComponent5`
- `list_components()` → `IAssemblyDoc::GetComponents`
- `add_mate(type: str, entity1: str, entity2: str, flip: bool, distance: float | None)` → `IAssemblyDoc::AddMate5`
- `delete_mate(mate_name: str)` → `IAssemblyDoc::DeleteMate`

---

### 3.11 Bounding Box

**Why needed:** Knowing a model's bounding box is essential for packaging, clearance checks, shipping box sizing, and aligning components in an assembly. Currently no tool exposes this.

**Tools to add:**
- `get_bounding_box()` → `IModelDoc2::GetBox` → returns min/max XYZ in metres

---

### 3.12 Shell Feature

**Why needed:** Shelling is the standard way to make a solid into a hollow enclosure (product housings, cases, cups). Currently the only way to hollow a part is manual sketch+cut operations.

**Tools to add:**
- `create_shell(thickness: float, face_names: list[str])` → `IFeatureManager::InsertShell`

---

### 3.13 Drawing Views (Real COM Calls)

**Why needed:** All current drawing tools (`create_drawing_view`, `add_dimension`, `create_section_view`, etc.) return simulated data without touching SolidWorks. A real COM-backed drawing view creation path is needed.

**Adapter work required:**
- Implement `create_drawing_view_real` in `io.py` or a new `drawing.py` adapter mixin using `IDrawingDoc::CreateDrawViewFromModelView3`
- Implement `create_section_view_real` using `IDrawingDoc::CreateSectionView5`
- Implement `create_projection_view` using `IDrawingDoc::CreateProjectionView`

---

### 3.14 Sheet Metal Tools

**Why needed:** Sheet metal is a major SW workflow. The current server has zero sheet metal capability. DXF flat pattern export is a common requirement for laser/plasma cutting.

**Tools to add (in order of priority):**
1. `insert_base_flange(sketch_name: str, thickness: float, bend_radius: float)` → `IFeatureManager::InsertBaseFlange2`
2. `insert_edge_flange(edge_name: str, width: float, angle: float)` → `IFeatureManager::InsertEdgeFlange2`
3. `flatten_sheet_metal()` → `IPartDoc::FlattenBends`
4. `export_flat_pattern_dxf(file_path: str)` → `IModelDoc2::ExportFlatPatternView`

---

### 3.15 Equation Manager

**Why needed:** Parametric designs driven by equations and global variables are a cornerstone of engineering-grade SW usage. Currently `get_dimension`/`set_dimension` only handles hard-coded dimension values, not formula-driven ones.

**Tools to add:**
- `list_equations()` → `IEquationMgr::GetEquationCount` + `GetEquation`
- `set_equation(name: str, formula: str)` → `IEquationMgr::SetEquation`
- `get_equation(name: str)` → `IEquationMgr::GetEquation`
- `delete_equation(name: str)` → `IEquationMgr::DeleteEquation`

---

## 4. Missing Medium/Low Priority Tools

### 4.1 Medium Priority

| Feature | SW API Method | Notes |
|---|---|---|
| Reference plane creation | `IFeatureManager::InsertRefSurface` | Required for off-axis sketches |
| Reference axis | `IFeatureManager::InsertRefAxis` | Needed for circular patterns |
| Cut-revolve | `IFeatureManager::FeatureCutRevolve2` | Complement to `create_revolve` |
| Cut-sweep | `InsertCutSwept3` | Swept cut |
| Cut-loft | `InsertCutBlend` | Lofted cut |
| `InsertThicken` | `IFeatureManager::InsertThicken` | Thicken surface to solid |
| List faces / face area | `IBody2::GetFaces` / `IFace2::GetArea` | Geometry inspection |
| 3MF export | `IModelDoc2::SaveAs4` with 3MF type | 3D printing |
| Import STEP/IGES | `ISldWorks::OpenDoc6` with neutral format | Receive supplier files |
| Select active document | `ISldWorks::ActivateDoc3` | Multi-document workflows |
| List open documents | `ISldWorks::GetDocuments` | Multi-document context |
| Ordinate dimensions (drawing) | `IModelDocExtension::AddOrdinateDimension` | Drawing chain dims |
| Hole callout (drawing) | `IModelDocExtension::AddHoleCallout` | Auto hole annotation |
| BOM table | `IDrawingDoc::AddBomTable4` | Assembly documentation |
| Update file references | `ISldWorks::ReplaceReferencedDocument` | Reference repair |
| 3D sketch | `ISketchManager::Insert3DSketch` | Space curves |
| Sketch text | `ISketchManager::InsertSketchText` | Engraved labels |
| Sketch split | `ISketchManager::SketchSplit` | Split entity at a point |
| Sketch fillet | `ISketchManager::SketchFillet` | Round corners in sketch |
| Display states | `IDisplayStateMgr` | Per-config appearance |

### 4.2 Low Priority

| Feature | SW API Method | Notes |
|---|---|---|
| Rib feature | `IFeatureManager::InsertRib` | Plastic-part ribs |
| Dome feature | `IFeatureManager::InsertDome` | Curved dome |
| Split body | `IFeatureManager::InsertSplit` | Multi-body splitting |
| Wrap feature | `IFeatureManager::InsertWrap2` | Wrap sketch on curved surface |
| Deform feature | `IFeatureManager::InsertDeform` | Flex/deform body |
| Freeform surface | `IFeatureManager::InsertFreeform` | Push-pull surface |
| Weldments | `IFeatureManager::InsertStructuralMember` | Structural member |
| Component patterns (assembly) | `InsertLinearComponentPattern` | Repeat component |
| Mirror component (assembly) | `InsertMirrorComponent` | Mirror in assembly |
| Explode view | `IAssemblyDoc::ExplodeView` | Exploded assembly view |
| Auto-explode | `IAssemblyDoc::AutoExplode` | Auto-generate explode |
| Render (PhotoView) | `ISldWorks::GetAddInObject("SldWorks.Application.PhotoView360")` | High-fidelity render |
| Set body color | `IModelDocExtension::SetUserPreferenceTextValue` | Appearance |
| eDrawings export | `ISldWorks::RunCommand` | eDrawings publish |
| OBJ/VRML/AMF export | `IModelDoc2::SaveAs4` | Mesh formats |
| Dynamic mirror sketch | `ISketchManager::InsertSketchMirror` | Live symmetry |
| Sketch picture | `ISketchManager::InsertSketchPicture` | Image reference |
| Print drawing | `IModelDoc2::Print3` | Paper/plotter output |
| Add-in management | `ISldWorks::GetAddInObject` | Add-in integration |
| FEA stub | SW Simulation COM API | Requires Simulation license |
| Motion study | SW Motion COM API | Requires Motion license |
| Flow simulation | SW Flow COM API | Requires Flow license |
| Material library management | Filesystem scan + DB | List available materials |
| Derived configurations | `IModelDoc2::AddConfiguration3` with parent | Config families |
| Export revision table | `IRevisionTable` | Drawing revision history |
| Layer management (drawing) | `ILayerMgr` | Drawing layer control |

---

## 5. Summary Table

| SW API Category | Approx. API Operations | Implemented (real COM) | Implemented (simulated) | Missing | % Real Coverage |
|---|---|---|---|---|---|
| Application (`ISldWorks`) | 30 | 6 | 1 | 23 | 20% |
| Document core (`IModelDoc2`) | 40 | 18 | 2 | 20 | 45% |
| Part (`IPartDoc`) | 25 | 2 | 1 | 22 | 8% |
| Assembly (`IAssemblyDoc`) | 30 | 1 | 1 | 28 | 3% |
| Drawing (`IDrawingDoc`) | 50 | 0 | 20 | 30 | 0% |
| Sketch (`ISketchManager`) | 35 | 17 | 0 | 18 | 49% |
| Feature Manager (`IFeatureManager`) | 45 | 7 | 0 | 38 | 16% |
| Configuration (`IConfiguration`) | 20 | 1 | 1 | 18 | 5% |
| Selection (`ISelectionMgr`) | 15 | 5 | 0 | 10 | 33% |
| Equations (`IEquationMgr`) | 10 | 0 | 0 | 10 | 0% |
| Mass Properties (`IMassProperty`) | 10 | 7 | 0 | 3 | 70% |
| Geometry / Topology (`IFace2`, `IEdge`) | 20 | 0 | 0 | 20 | 0% |
| Materials (`IMaterial`) | 10 | 0 | 1 | 9 | 0% |
| Reference Geometry | 10 | 1 | 0 | 9 | 10% |
| Appearances / Display | 15 | 0 | 0 | 15 | 0% |
| Export formats | 20 | 6 | 1 | 13 | 30% |
| Import formats | 10 | 0 | 0 | 10 | 0% |
| Pack and Go / References | 10 | 5 | 0 | 5 | 50% |
| Macros / VBA | 8 | 0 | 3 | 5 | 0% |
| Simulation / FEA / Flow | 20 | 0 | 0 | 20 | 0% |
| **TOTAL** | **~433** | **~76** | **~31** | **~326** | **~18%** |

> **Note on "simulated":** Tools marked simulated accept parameters and return plausible-looking responses but do not make any COM calls to SolidWorks. They will not modify a real document. These are stubs awaiting a real implementation.

> **Note on counting:** "API operations" are counted at the granularity of meaningful user-facing operations (not every individual overload of every COM method). The ~433 figure is an estimate derived from the major interface areas; the actual SW API has thousands of individual method signatures.

---

### Recommended Implementation Sequence

Based on impact and dependency order:

1. **`add_chamfer` MCP tool** — 1 hour; adapter code already written
2. **Real custom properties** (`get_custom_properties`, `set_custom_property`) — 1 day
3. **Configuration switching** (`switch_configuration`, `get_active_configuration`) — 1 day  
4. **`set_material` / `get_material`** — 1 day
5. **Feature patterns** (linear, circular, mirror) — 2 days
6. **Hole Wizard** — 1 day
7. **`sketch_trim` / `sketch_convert_entities`** — 1 day
8. **Reference plane / axis creation** — 1 day
9. **Shell feature** — 0.5 days
10. **Bounding box** — 0.5 days
11. **Assembly: insert component + add mate** — 3 days
12. **Equation Manager** — 2 days
13. **Real drawing view creation** (COM-backed) — 3 days
14. **Sheet metal (base flange, edge flange, flatten, DXF export)** — 3 days
15. **Run macro** — 0.5 days
