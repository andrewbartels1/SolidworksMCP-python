# SolidWorks MCP Server

Python MCP server for SolidWorks automation with 90+ tools (modeling, sketching, drawing, export, analysis, automation, templates, and macros).

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://www.microsoft.com/windows)
[![SolidWorks](https://img.shields.io/badge/SolidWorks-2019--2025-red)](https://www.solidworks.com/)

## Choose Your Setup Path

| Path | Use case | SolidWorks required | Recommended commands |
| --- | --- | --- | --- |
| Windows only | Real CAD automation on one machine | Yes | Conda + PowerShell |
| Linux/WSL only | Mock-mode dev, tests, docs | No | Make |
| WSL/Linux + Windows host | Client/dev on Linux, real CAD on Windows | Windows host only | Make (Linux side) + PowerShell (Windows host) |

## Requirements

- Python 3.11+
- One environment manager: conda, mamba, or micromamba
- Windows 10/11 + SolidWorks 2019+ for real COM automation

Maker note: SolidWorks Maker is for non-commercial personal use and is commonly described as limited to $2,000 USD annual profit. Verify current license terms directly with SolidWorks before production use.

## Quick Start (Step-by-Step)

### Option A: Windows only (real SolidWorks automation)

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python

conda create -n solidworks_mcp python=3.11
conda activate solidworks_mcp
pip install -e ".[dev,test,docs]"

pytest
python -m solidworks_mcp.server
```

### Option B: Linux/WSL only (mock mode mcp host and docs)

```bash
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python

make install
make test
make docs
```

### Option C: WSL/Linux client + Windows SolidWorks host

1. On Windows host, install SolidWorks and run:

```powershell
python -m solidworks_mcp.server --mode remote --host 0.0.0.0 --port 8000
```

1. On WSL/Linux client, develop/test with:

```bash
make install
make test
```

1. Connect your client to http://<windows-host-ip>:8000.

## Common Commands

### Linux/WSL (Make)

```bash
make install
make test
make docs
make run
make lint
make format
```

### Windows PowerShell (direct)

```powershell
conda activate solidworks_mcp
pytest --cov=solidworks_mcp
python -m solidworks_mcp.server
python -m solidworks_mcp.server --mock
python -m solidworks_mcp.server --mode remote --host 0.0.0.0 --port 8000
```

## Documentation

- [docs/index.md](docs/index.md)
- [docs/getting-started/installation.md](docs/getting-started/installation.md)
- [docs/getting-started/quickstart.md](docs/getting-started/quickstart.md)
- [docs/user-guide/architecture.md](docs/user-guide/architecture.md)
- [docs/user-guide/tools-overview.md](docs/user-guide/tools-overview.md)

## License

MIT License. See [LICENSE](LICENSE).
0
## TODO (& Next Steps)

- [ ] Add end-to-end load/save smoke coverage for parts and assemblies in real SolidWorks integration tests.
- [ ] Add dedicated tools for explicit document lifecycle operations (load part, load assembly, save active, save as, save all).
- [ ] Add tool-level safeguards for save targets (path validation, overwrite policy, extension checks).
- [ ] Add a docs discovery tool that indexes all available COM and VBA commands for the installed SolidWorks version.
- [ ] Support local documentation query mode for SolidWorks Help/API references when context is too large for prompt input.
- [ ] Evaluate optional RAG backend for docs discovery (sqlite-vec, LangChain, or equivalent local vector index).
- [ ] Add deterministic regression tests for docs discovery against known COM/VBA symbols.
