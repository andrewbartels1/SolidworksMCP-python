# SolidWorks MCP Server

A Python Model Context Protocol (MCP) server for SolidWorks automation, focused on CAD workflows, testable local development, and documentation-driven setup.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green?logo=anthropic)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://www.microsoft.com/windows)
[![SolidWorks](https://img.shields.io/badge/SolidWorks-2019--2025-red)](https://www.solidworks.com/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-0A66C2)](https://andrewbartels1.github.io/SolidworksMCP-python/)
[![Tests](https://github.com/andrewbartels1/SolidworksMCP-python/actions/workflows/ci.yml/badge.svg)](https://github.com/andrewbartels1/SolidworksMCP-python/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python/branch/main/graph/badge.svg)](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python)

## Overview

This repository contains the Python implementation of the SolidWorks MCP server. It provides 90+ tools across modeling, sketching, drawing, export, analysis, automation, templates, and macro workflows.

The project is still evolving. Expect some rough edges, but the current direction is Python-first, FastMCP-based, and documented through MkDocs.

## Motivation and Origins

This project exists to explore a Python-first approach to SolidWorks automation through MCP, with an emphasis on local development, clearer documentation, testability, and experimentation around CAD-focused agent workflows.

It is also directly inspired by the original TypeScript project created by vespo92. If you are looking for the original concept, earlier implementation approach, or the upstream source that sparked this rewrite, see:

- Original repository: https://github.com/vespo92/SolidworksMCP-TS

This repository is an independent Python implementation rather than a continuation of that TypeScript codebase, but the original project deserves clear credit for the initial idea and direction.

## What This Repo Is

- A Python MCP server for SolidWorks automation
- A local development and learning project for FastMCP, LLM tooling, and CAD workflows
- A documented codebase with tests, examples, and a MkDocs site

## Requirements

- Windows 10 or 11 for real SolidWorks automation
- SolidWorks 2019+ for live COM-backed workflows
- Python 3.11+
- `conda`, `mamba`, or `micromamba` available on your machine for the provided `make` commands

Notes:

- On Linux or WSL, you can still run tests, docs, and mock-mode development workflows.
- Real SolidWorks integration requires Windows with SolidWorks installed.

## Quick Start

```bash
git clone git@github.com:andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python

make install
make test
make docs
```

The docs server runs at `http://localhost:8000`.

## Common Commands

Use the Makefile as the main entrypoint for day-to-day work:

```bash
make install   # install dependencies and set up the environment
make test      # run the test suite with coverage
make docs      # serve MkDocs locally at http://localhost:8000
make run       # start the MCP server
make build     # build the package
make lint      # run Ruff checks
make format    # format source and tests
make clean     # remove build and test artifacts
```

If you want the full command list:

```bash
make help
```

## Documentation

The MkDocs site is the primary source of truth for setup and usage.

Start here:

- [docs/index.md](docs/index.md)
- [docs/getting-started/installation.md](docs/getting-started/installation.md)
- [docs/getting-started/quickstart.md](docs/getting-started/quickstart.md)
- [docs/user-guide/architecture.md](docs/user-guide/architecture.md)
- [docs/user-guide/tools-overview.md](docs/user-guide/tools-overview.md)

For local browsing:

```bash
make docs
```

## Tool Coverage

The server currently includes tools across these areas:

- Modeling
- Sketching
- Drawing
- Drawing analysis
- Analysis
- Export
- Automation
- File management
- VBA generation
- Template management
- Macro recording

Tool discovery and validation utilities live under [src/utils](src/utils).

## Development Workflow

Typical local workflow:

```bash
make install
make test
make docs
make run
```

For direct utility scripts when needed:

```bash
python src/utils/validate_coverage.py
python src/utils/verify_tool_count.py
python src/utils/start_local_server.py --help
```

## Testing

Tests are designed to run in mock mode by default for cross-platform development.

```bash
make test
python src/utils/validate_coverage.py
```

If you are working on documentation or tool inventory, these are also useful:

```bash
python src/utils/verify_tool_count.py
make docs
```

## Claude Desktop / MCP Clients

For client setup and configuration examples, use the documentation rather than this README:

- [docs/getting-started/quickstart.md](docs/getting-started/quickstart.md)
- [docs/user-guide/tools-overview.md](docs/user-guide/tools-overview.md)

That keeps configuration examples in one maintained place.

## Project Status

This is an active work-in-progress project. The Python implementation is the only supported implementation described in this repository.

## License

MIT License. See [LICENSE](LICENSE).
