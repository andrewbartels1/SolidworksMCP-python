# Tools Overview

The SolidWorks MCP Server provides 90+ specialized tools for comprehensive CAD automation. Each tool is designed with enterprise-grade reliability, extensive error handling, and intelligent parameter validation.

## Tool Categories

<div class="grid cards" markdown>

- :material-cube-outline:{ .lg .middle } **Modeling Tools**

    ---

    Core 3D modeling operations including part creation, features, assemblies, and configurations.

    [**9 tools available** :octicons-arrow-right-24:](#modeling-tools)

- :material-pencil:{ .lg .middle } **Sketching Tools**

    ---

    Complete 2D sketching toolkit with geometry creation, constraints, and dimensions.

    [**17 tools available** :octicons-arrow-right-24:](#sketching-tools)

- :material-technical-draw:{ .lg .middle } **Drawing Tools**

    ---

    Technical drawing creation, view management, dimensions, and annotations.

    [**8 tools available** :octicons-arrow-right-24:](#drawing-tools)

- :material-chart-line:{ .lg .middle } **Analysis Tools**

    ---

    Mass properties, interference checking, structural analysis, and validation.

    [**4 tools available** :octicons-arrow-right-24:](#analysis-tools)

- :material-export:{ .lg .middle } **Export Tools**

    ---

    Multi-format export including STEP, IGES, STL, PDF, DWG, and image formats.

    [**7 tools available** :octicons-arrow-right-24:](#export-tools)

- :material-code-braces:{ .lg .middle } **VBA Generation**

    ---

    Dynamic VBA code generation for complex operations exceeding COM parameter limits.

    [**10 tools available** :octicons-arrow-right-24:](#vba-generation)

- :material-file-document:{ .lg .middle } **Template Management**

    ---

    Template creation, extraction, application, comparison, and library management.

    [**6 tools available** :octicons-arrow-right-24:](#template-management)

- :material-record:{ .lg .middle } **Macro Recording**

    ---

    Macro recording, playback, analysis, optimization, and library creation.

    [**8 tools available** :octicons-arrow-right-24:](#macro-recording)

- :material-magnify:{ .lg .middle } **Drawing Analysis**

    ---

    Quality analysis, dimension checking, compliance verification, and reporting.

    [**10 tools available** :octicons-arrow-right-24:](#drawing-analysis)

- :material-cog:{ .lg .middle } **Automation Tools**

    ---

    Workflow orchestration, batch processing, and automated file operations.

    [**8 tools available** :octicons-arrow-right-24:](#automation-tools)

</div>

## Tool Statistics

| Category | Tool Count | Complexity Level | Primary Use Case |
|----------|------------|------------------|------------------|
| **Modeling** | 9 | High | Part/assembly creation and modification |
| **Sketching** | 17 | Medium | 2D geometry and constraint management |
| **Drawing** | 8 | Medium | Technical documentation creation |
| **Drawing Analysis** | 10 | Medium | Quality assurance and compliance |
| **Analysis** | 4 | High | Engineering validation and analysis |
| **Export** | 7 | Low | File format conversion and sharing |
| **Automation** | 8 | High | Workflow orchestration and batch processing |
| **File Management** | 3 | Low | File operations and organization |
| **VBA Generation** | 10 | Very High | Complex operation automation |
| **Template Management** | 6 | Medium | Standardization and reuse |
| **Macro Recording** | 8 | High | Workflow capture and optimization |

**Total: 90+ Tools**

## Tool Design Principles

### 1. Intelligent Parameter Handling

Each tool automatically determines the optimal execution strategy:

```python
@mcp.tool()
async def create_extrusion(
    sketch_name: str,
    depth: float,
    direction: str = "Blind",
    reverse_direction: bool = False,
    # 20+ additional parameters...
) -> dict[str, Any]:
    """Create an extrusion feature.
    
    Automatically routes to VBA generation for complex parameter sets.
    """
```

### 2. Comprehensive Error Handling

All tools include robust error handling with detailed feedback:

- **Parameter Validation**: Pydantic models ensure type safety
- **SolidWorks Integration**: Graceful handling of COM failures
- **Fallback Strategies**: Automatic retry with alternative approaches
- **Detailed Logging**: Complete audit trail of all operations

### 3. Security-First Design

Tools respect the configured security level:

```python
# Example security enforcement
@security_check(level="elevated")
@mcp.tool()
async def batch_export(...):
    # Only available in development/restricted modes
    pass

@security_check(level="safe")  
@mcp.tool()
async def calculate_mass_properties(...):
    # Available in all security modes
    pass
```

## Common Patterns

### Async/Await Support

All tools are fully asynchronous for optimal performance:

```python
# Non-blocking tool execution
result = await create_part("MyPart", template="Part Template")
mass_props = await calculate_mass_properties("current")
```

### Result Standardization

Consistent return format across all tools:

```python
{
    "status": "success",
    "message": "Operation completed successfully",
    "data": {
        "feature_id": "Extrude1",
        "geometry": {...},
        "properties": {...}
    },
    "execution_time": 0.234,
    "adapter_used": "VBA Generator"
}
```

### Progress Tracking

Long-running operations provide real-time progress:

```python
# Tools support progress callbacks
async def progress_callback(progress: float, message: str):
    print(f"Progress: {progress:.1%} - {message}")

result = await batch_process_files(
    files=file_list,
    on_progress=progress_callback
)
```

## Tool Selection Guide

### By Use Case

#### Getting Started

- **Simple modeling**: `create_part()`, `create_sketch()`, `create_extrusion()`
- **Basic analysis**: `calculate_mass_properties()`, `measure_distance()`
- **File operations**: `save_document()`, `export_step()`

#### Intermediate Usage  

- **Complex features**: `create_sweep()`, `create_loft()`, `create_pattern()`
- **Drawing creation**: `create_technical_drawing()`, `add_drawing_view()`
- **Batch operations**: `batch_export()`, `batch_process_files()`

#### Advanced Automation

- **Workflow orchestration**: `execute_workflow()`, `generate_vba_code()`
- **Template management**: `extract_template()`, `apply_template()`
- **Macro optimization**: `optimize_macro()`, `analyze_macro()`

### By Security Level

#### Development (All Tools)

Full access to all 90+ tools for maximum functionality.

#### Restricted (74 Tools)

Safe and moderate tools excluding system-level operations:

- ✅ All modeling and sketching tools
- ✅ Drawing tools and analysis
- ✅ Export and file management
- ❌ System VBA execution
- ❌ Advanced macro recording

#### Secure (45 Tools)  

Read-only and analysis tools for production environments:

- ✅ Analysis and measurement tools
- ✅ Read-only property access
- ✅ Export operations
- ❌ Modeling modifications
- ❌ File system write access

#### Locked (15 Tools)

Minimal analysis tools for public interfaces:

- ✅ Mass properties and measurements
- ✅ Basic geometric analysis
- ❌ All modification operations
- ❌ File system access

## Performance Characteristics

### Operation Speed

| Tool Category | Avg Response Time | Complexity Factor |
|---------------|-------------------|-------------------|
| Property Queries | 50-100ms | 1x |
| Simple Geometry | 100-300ms | 2x |
| Complex Features | 300-800ms | 5x |
| Batch Operations | 1-10s | 20x |
| VBA Generation | 200-500ms | 3x |

### Resource Usage

- **Memory**: 50-200MB per SolidWorks instance
- **CPU**: Varies by operation complexity
- **Disk**: Minimal for operations, substantial for exports
- **Network**: None (local SolidWorks integration)

---

## Detailed Tool Categories

## Modeling Tools {#modeling-tools}

:material-cube-outline: **9 Tools** | 3D modeling and part creation

### Core Tools

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `create_part` | Create new part document | Low | New part creation from templates |
| `create_assembly` | Create new assembly document | Low | Multi-part assembly setup |
| `create_extrude` | Create extrusion features | Medium | Basic 3D geometry creation |
| `create_revolve` | Create revolution features | Medium | Rotational geometry |
| `create_sweep` | Create swept features | High | Complex path-based geometry |
| `create_loft` | Create lofted features | High | Advanced surface modeling |
| `create_cut` | Create cut features | Medium | Material removal operations |
| `create_fillet` | Apply fillet/round features | Low | Edge finishing |
| `manage_configurations` | Handle design configurations | High | Design variant management |

### Example Usage

```python
# Create a new part
result = await create_part(
    name="Motor Housing",
    template="Part Template",
    units="millimeters"
)

# Add an extrusion
extrude = await create_extrude(
    sketch_name="Base Profile",
    depth=50.0,
    direction="Blind"
)
```

## Sketching Tools {#sketching-tools}

:material-pencil: **17 Tools** | 2D geometry and constraints

### Geometry Creation

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `create_sketch` | Initialize new sketch | Low | Start 2D design |
| `sketch_line` | Draw line segments | Low | Basic geometry |
| `sketch_rectangle` | Draw rectangles | Low | Rectangular profiles |
| `sketch_circle` | Draw circles | Low | Circular features |
| `sketch_arc` | Draw arcs | Medium | Curved geometry |
| `sketch_spline` | Draw splines | Medium | Complex curves |
| `sketch_polygon` | Draw polygons | Low | Multi-sided shapes |

### Constraints & Dimensions

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `add_dimension` | Add sketch dimensions | Medium | Size control |
| `add_constraint` | Add geometric constraints | Medium | Shape relationships |
| `constraint_coincident` | Coincident constraint | Low | Point alignment |
| `constraint_parallel` | Parallel constraint | Low | Line relationships |
| `constraint_perpendicular` | Perpendicular constraint | Low | Right angles |
| `constraint_tangent` | Tangent constraint | Medium | Smooth transitions |
| `constraint_equal` | Equal constraint | Low | Size matching |
| `constraint_symmetric` | Symmetry constraint | Medium | Balanced geometry |
| `sketch_pattern` | Pattern sketch entities | High | Repeated geometry |

### Example Usage

```python
# Create and populate a sketch
sketch = await create_sketch(plane="Front")
await sketch_rectangle(
    center_x=0, center_y=0,
    width=100, height=50
)
await add_dimension(
    entity="Rectangle",
    dimension_type="width",
    value=100
)
```

## Drawing Tools {#drawing-tools}

:material-technical-draw: **8 Tools** | Technical documentation

### View Management

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `create_drawing` | Create new drawing document | Low | Technical documentation |
| `insert_model_view` | Insert 3D model view | Medium | Show part/assembly |
| `create_section_view` | Create section views | High | Internal details |
| `create_detail_view` | Create detail views | Medium | Magnified areas |
| `arrange_views` | Auto-arrange drawing views | Medium | Layout optimization |

### Annotations

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `add_dimensions` | Add drawing dimensions | Medium | Size specification |
| `add_annotations` | Add notes and symbols | Low | Documentation |
| `create_title_block` | Manage title blocks | Medium | Drawing standards |

### Example Usage

```python
# Create drawing with views
drawing = await create_drawing(
    template="A3 Landscape",
    part_path="Motor Housing.SLDPRT"
)
await insert_model_view(
    view_type="Isometric",
    scale=0.5
)
```

## Analysis Tools {#analysis-tools}

:material-chart-line: **4 Tools** | Engineering analysis and validation

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `calculate_mass_properties` | Mass, volume, center of mass | Low | Weight analysis |
| `interference_detection` | Check part collisions | Medium | Assembly validation |
| `measure_entities` | Distances, angles, areas | Low | Geometric measurements |
| `validate_geometry` | Check model integrity | High | Quality assurance |

### Example Usage

```python
# Analyze part properties
props = await calculate_mass_properties(
    entities=["Part1", "Part2"],
    include_hidden=False
)
mass = props.data["mass"]
volume = props.data["volume"]
```

## Export Tools {#export-tools}

:material-export: **7 Tools** | File format conversion

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `export_step` | Export to STEP format | Low | CAD data exchange |
| `export_iges` | Export to IGES format | Low | Legacy CAD systems |
| `export_stl` | Export to STL format | Low | 3D printing |
| `export_pdf` | Export drawings to PDF | Medium | Documentation |
| `export_dxf` | Export 2D DXF files | Medium | 2D fabrication |
| `export_images` | Export to image formats | Low | Presentations |
| `batch_export` | Export multiple files | High | Mass conversion |

### Example Usage

```python
# Export for 3D printing
await export_stl(
    file_path="Motor Housing.stl",
    resolution="Fine",
    units="Millimeters"
)
```

## VBA Generation {#vba-generation}

:material-code-braces: **10 Tools** | Automatic VBA code generation

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `generate_macro` | Create VBA macro code | High | Complex operations |
| `optimize_macro` | Optimize existing macros | High | Performance tuning |
| `macro_to_api` | Convert macro to API calls | High | Code modernization |
| `validate_syntax` | Check VBA syntax | Medium | Code validation |
| `execute_vba` | Run VBA code safely | High | Custom operations |
| `macro_library` | Manage macro collections | Medium | Code organization |
| `parameter_mapping` | Map API to VBA params | High | Translation layer |
| `error_handling` | Add robust error handling | Medium | Reliability |
| `performance_analysis` | Analyze macro performance | High | Optimization |
| `code_documentation` | Generate macro docs | Low | Documentation |

## Template Management {#template-management}

:material-file-document: **6 Tools** | Standardized workflows

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `create_template` | Create document templates | Medium | Standardization |
| `apply_template` | Apply templates to docs | Low | Consistency |
| `extract_template` | Extract template from doc | Medium | Template creation |
| `validate_template` | Check template integrity | Medium | Quality control |
| `template_library` | Manage template collections | High | Organization |
| `compare_templates` | Compare template versions | Medium | Version control |

## Macro Recording {#macro-recording}

:material-record: **8 Tools** | Macro automation

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `start_recording` | Begin macro recording | Low | Capture workflows |
| `stop_recording` | End macro recording | Low | Save captured actions |
| `playback_macro` | Execute recorded macro | Medium | Automation replay |
| `edit_macro` | Modify macro code | High | Customization |
| `optimize_recording` | Improve macro efficiency | High | Performance |
| `macro_analysis` | Analyze macro quality | Medium | Code review |
| `create_macro_library` | Build macro collections | High | Organization |
| `share_macros` | Export/import macros | Medium | Collaboration |

## Drawing Analysis {#drawing-analysis}

:material-magnify: **10 Tools** | Quality assurance

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `check_dimensions` | Validate drawing dimensions | Medium | Quality control |
| `analyze_tolerances` | Check tolerance stack-up | High | Engineering analysis |
| `verify_standards` | Check drawing standards | Medium | Compliance |
| `detect_errors` | Find drawing issues | High | Error detection |
| `generate_reports` | Create analysis reports | Medium | Documentation |
| `compare_revisions` | Compare drawing versions | High | Version control |
| `validate_symbols` | Check symbol usage | Medium | Standard compliance |
| `measure_complexity` | Analyze drawing complexity | Medium | Metrics |
| `audit_properties` | Check document properties | Low | Metadata validation |
| `compliance_check` | Full compliance validation | High | Certification |

## Automation Tools {#automation-tools}

:material-cog: **8 Tools** | Workflow orchestration

| Tool Name | Description | Complexity | Use Case |
|-----------|-------------|------------|----------|
| `batch_process` | Process multiple files | High | Mass operations |
| `workflow_builder` | Create custom workflows | High | Process automation |
| `schedule_tasks` | Schedule automated tasks | Medium | Background processing |
| `file_operations` | Automated file management | Medium | File organization |
| `data_extraction` | Extract data from models | Medium | Data mining |
| `report_generation` | Create automated reports | High | Documentation |
| `integration_apis` | Connect external systems | High | System integration |
| `monitoring_tools` | Monitor automation health | Medium | System management |

---

## Best Practices

### Tool Selection

1. **Use the right tool**: Choose the most specific tool for your task
2. **Consider security**: Select appropriate security level for deployment
3. **Handle errors**: Always check return status and handle failures
4. **Monitor performance**: Track execution times for optimization

### Batch Operations

1. **Group similar operations**: Batch similar tasks for efficiency
2. **Manage resources**: Consider SolidWorks memory usage
3. **Implement progress tracking**: Provide user feedback for long operations
4. **Error recovery**: Handle partial failures gracefully

### Security Considerations

1. **Least privilege**: Use the lowest security level that meets requirements
2. **Validate inputs**: Always validate user-provided parameters
3. **Audit operations**: Log all operations for compliance
4. **Monitor access**: Track tool usage patterns

---

!!! tip "Getting Started"
    Ready to explore? Jump to any tool category above or check out the [Quick Start Guide](../getting-started/quickstart.md) for hands-on examples.

!!! info "Development Status"
    All 90+ tools are implemented and ready for use. Documentation and examples are continuously being expanded.
