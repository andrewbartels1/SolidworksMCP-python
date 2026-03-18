# Quick Start Guide

Get up and running with SolidWorks automation in under 5 minutes!

## Prerequisites Check

Before starting, ensure you have:

- ✅ Python 3.11+
- ✅ One environment manager: conda, mamba, or micromamba
- ✅ Windows 10/11 with SolidWorks installed for real automation
- ✅ Linux/WSL if you want mock-mode development or a remote client workflow

## Choose Your Path

### Option A: Windows only

Use this when SolidWorks and the MCP server run on the same Windows machine.

### Option B: Linux / WSL only

Use this for mock-mode development, tests, and docs. Real COM automation is not available in this path.

### Option C: Linux / WSL client + Windows host

Use this when SolidWorks runs on Windows and your MCP client or development workflow runs on Linux/WSL.

## 1. Installation (2 minutes)

### Option A: Windows only

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
conda create -n solidworks_mcp python=3.11
conda activate solidworks_mcp
pip install -e ".[dev,test,docs]"
```

### Option B: Linux / WSL only

```bash
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
make install
```

### Option C: Linux / WSL client + Windows host

1. On the Windows host:

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
conda create -n solidworks_mcp python=3.11
conda activate solidworks_mcp
pip install -e ".[dev,test,docs]"
python -m solidworks_mcp.server --mode remote --host 0.0.0.0 --port 8000
```

2. On the Linux/WSL machine:

```bash
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
make install
make test
```

3. Point your client to `http://<windows-host-ip>:8000`.

## 2. First Automation (2 minutes)

### Start SolidWorks

Launch SolidWorks before running the MCP server on the Windows host.

- Option A: launch SolidWorks locally on the same Windows machine.
- Option B: skip this step and use mock mode.
- Option C: launch SolidWorks on the Windows host, not inside Linux/WSL.

### Test Connection

Use this Python check for Option A or Option C on the Windows host:

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

For Option B, validate the local development setup with:

```bash
make test
make run
```

### Run Your First Tool

Run this on Windows where the SolidWorks adapter is available:

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

python utils/verify_tool_count.py

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

### Windows Environment Issues

```powershell
# Clean reinstall
conda env remove -n solidworks_mcp
conda create -n solidworks_mcp python=3.11
conda activate solidworks_mcp
pip install -e ".[dev,test,docs]"
```

### Linux / WSL Environment Issues

```bash
make install
make test
```

### WSL / Linux Cannot Reach Windows Host

- Ensure the Windows host is running `python -m solidworks_mcp.server --mode remote --host 0.0.0.0 --port 8000`.
- Use the Windows host IP address instead of `localhost` when needed.
- Confirm Windows Firewall allows inbound connections on port 8000.

### Permission Issues

- Ensure SolidWorks is running before connecting

---

**Ready for more?** → [Architecture Guide](../user-guide/architecture.md) to understand the system design
