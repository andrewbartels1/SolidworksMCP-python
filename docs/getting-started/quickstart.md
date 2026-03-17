# Quick Start Guide

Get up and running with SolidWorks automation in under 5 minutes!

## Prerequisites Check

Before starting, ensure you have:

- ✅ Windows 10/11

- ✅ SolidWorks 2020+ installed

- ✅ Python 3.12+ (conda recommended)

- ✅ Administrator privileges

## 1. Installation (2 minutes)

```bash

# Clone and setup

git clone https://github.com/yourusername/SolidworksMCP-python.git

cd SolidworksMCP-python



# Automated setup with mamba/conda

make install



# Activate environment

mamba activate solidworks_mcp

uv pip install -e ".[dev,test,docs]"

```

## 2. First Automation (2 minutes)

### Start SolidWorks

Launch SolidWorks before running the MCP server.

### Test Connection

```python

from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

from solidworks_mcp.config import load_config



# Initialize adapter

config = load_config()

adapter = PyWin32Adapter(config)



# Connect to SolidWorks

result = adapter.connect()

print(f\"Connection status: {result['status']}\")



# Get SolidWorks info

info = adapter.get_application_info()

print(f\"SolidWorks Version: {info.get('version')}\")

```

### Run Your First Tool

```python

from solidworks_mcp.tools.sketching import create_sketch

# Create a new part

part_result = adapter.create_new_document(\"part\")

print(f\"New part created: {part_result['message']}\")

# Create a sketch

sketch_result = adapter.create_sketch(\"Front Plane\")

print(f\"Sketch created: {sketch_result['message']}\")

# Add a rectangle

rect_result = adapter.add_rectangle(0, 0, 50, 30)

print(f\"Rectangle added: {rect_result['message']}\")

```

## 3. Explore Tools (1 minute)

### Check Available Tools

```bash

python verify_tool_count.py

```

Expected output:

```

SolidWorks MCP Server Tool Count Verification

==================================================

Modeling: 9 tools

Sketching: 17 tools

Drawing: 8 tools

Drawing Analysis: 10 tools

... (and more)

==================================================

Total Tools: 90+

Status: ✓ TARGET ACHIEVED

```

### Tool Categories Overview

#### Modeling Tools

    ```python

    # Create features

    adapter.create_extrusion({\"distance\": 10, \"direction\": \"up\"})

    adapter.create_revolve({\"angle\": 360, \"axis\": \"center_line\"})

    adapter.add_fillet({\"radius\": 2, \"edges\": [\"edge1\", \"edge2\"]})

```



#### Sketching Tools

    ```python

    # Create geometry

    adapter.add_line(0, 0, 100, 0)  # Horizontal line

    adapter.add_circle(50, 50, 25)  # Circle

    adapter.add_arc(0, 0, 50, 50, 100, 0)  # Arc

    

    # Add constraints

    adapter.add_sketch_constraint(\"parallel\", [\"line1\", \"line2\"])

```

#### Analysis Tools

    ```python

    # Get mass properties

    properties = adapter.get_mass_properties()

    print(f\"Volume: {properties['volume']} cubic mm\")

    print(f\"Mass: {properties['mass']} kg\")

```



#### Export Tools

    ```python

    # Export to different formats

    adapter.export_step(\"output.step\")

    adapter.export_pdf(\"drawing.pdf\")

    adapter.export_stl(\"model.stl\")

```

## 4. Advanced Examples

### Automated Part Creation

```python

# Create a parametric bracket

def create_bracket(width=50, height=30, thickness=5):

    # Create new part
    adapter.create_new_document(\"part\")

    

    # Create base sketch
    adapter.create_sketch(\"Front Plane\")
    adapter.add_rectangle(0, 0, width, height)

    

    # Add mounting holes
    hole_spacing = width * 0.8
    adapter.add_circle(width*0.1, height*0.1, 2.5)  # M5 hole
    adapter.add_circle(width*0.9, height*0.1, 2.5)  # M5 hole
    adapter.exit_sketch()


    # Extrude base
    adapter.create_extrusion({
        \"distance\": thickness,
        \"direction\": \"up\",
        \"operation\": \"new_body\"

    })

    # Add fillets
    adapter.add_fillet({\"radius\": 2, \"select_all_edges\": True})

    return \"Bracket created successfully!\"



# Run the automation

result = create_bracket(60, 40, 8)

print(result)

```

### Batch Processing

```python

def batch_export_drawings():

    \"\"\"Export all drawings in a folder to PDF.\"\"\"

    import os

    folder = \"C:/SolidWorks_Files/Drawings\"
    output_folder = \"C:/Exports/PDFs\"

    

    for file in os.listdir(folder):
        if file.endswith(\".slddrw\"):
            # Open drawing
            adapter.open_document(os.path.join(folder, file))

            # Export to PDF
            pdf_name = file.replace(\".slddrw\", \".pdf\")
            adapter.export_pdf(os.path.join(output_folder, pdf_name))

            

            # Close document
            adapter.close_document()

    return f\"Exported drawings from {folder}\"



batch_export_drawings()

```

## 5. What's Next?

### Documentation

- [**Architecture Overview**](../user-guide/architecture.md) - Understand the system design
- [**Tools Overview**](../user-guide/tools-overview.md) - Explore all 90+ available tools

### Advanced Features

- **VBA Generation** - Complex operations with VBA (automatically handled)
- **Template Management** - Standardize workflows (coming soon)
- **Macro Recording** - Record and optimize macros (coming soon)

### Development

- **Contributing** - Add your own tools (documentation coming soon)
- **Testing** - Test your automations (documentation coming soon)

---

## Troubleshooting Quick Fixes

### SolidWorks Connection Issues

```bash
# Re-register COM (run as Administrator)
regsvr32 "C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\sldworks.tlb"
```

### Environment Issues

```bash
# Clean reinstall
mamba env remove -n solidworks_mcp
make install
```

### Permission Issues

- Ensure SolidWorks is running before connecting

---

**Ready for more?** → [Architecture Guide](../user-guide/architecture.md) to understand the system design
