# SolidWorks MCP Server

> ⚠️ **Project Status:** This project is under active construction. Features, APIs, documentation, and setup steps may change as the Python implementation is finalized. ⚠️

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green?logo=anthropic)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://www.microsoft.com/windows)
[![SolidWorks](https://img.shields.io/badge/SolidWorks-2019--2025-red)](https://www.solidworks.com/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-0A66C2)](https://andrewbartels1.github.io/SolidworksMCP-python/)
[![Tests](https://github.com/andrewbartels1/SolidworksMCP-python/actions/workflows/ci.yml/badge.svg)](https://github.com/andrewbartels1/SolidworksMCP-python/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python/branch/main/graph/badge.svg)](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python)

**The Complete Python MCP Server for SolidWorks Automation**

🚀 **90+ Tools** | 🧠 **Intelligent Architecture** | ⚡ **Auto VBA Fallback** | 🔒 **Security-First**

## Overview

A comprehensive Model Context Protocol (MCP) server for SolidWorks automation, featuring intelligent COM/VBA routing, enterprise-grade security, and 90+ professional tools covering all aspects of CAD workflow automation.

## 🔥 Key Innovations

### Intelligent COM Bridge

Solves the traditional CAD automation challenge where COM interfaces fail with complex operations (13+ parameters):

- **Simple operations** → Direct COM API (fastest)
- **Complex operations** → Automatic VBA generation (reliable)  
- **Failed operations** → Circuit breaker fallback patterns

### Enterprise-Grade Security

Four-tier security model for different deployment scenarios:

- **Development** - Full access for local development
- **Restricted** - Controlled access for internal tools
- **Secure** - Production-ready with read-only operations
- **Locked** - Minimal access for public interfaces

## Quick Start

Choose the path that matches your setup:

### Windows only

Use this when SolidWorks and the MCP server run on the same Windows machine.

```powershell
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
conda create -n solidworks_mcp python=3.11
conda activate solidworks_mcp
pip install -e ".[dev,test,docs]"
python -m solidworks_mcp.server
```

### Linux / WSL only

Use this for mock-mode development, tests, and documentation work.

```bash
git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
cd SolidworksMCP-python
make install
make test
make docs
```

### Linux / WSL client + Windows host

Use this when SolidWorks runs on Windows and your client or development workflow runs on Linux/WSL.

```powershell
python -m solidworks_mcp.server --mode remote --host 0.0.0.0 --port 8000
```

```bash
make install
make test
```

Then connect your client to `http://<windows-host-ip>:8000`.

## Tool Categories

| Category | Tools | Description |
|----------|-------|-------------|
| **Modeling** | 9 | Part creation, features, assemblies |
| **Sketching** | 17 | Complete sketching toolkit with constraints |
| **Drawing** | 8 | Drawing creation and management |
| **Drawing Analysis** | 10 | Quality analysis and compliance checking |
| **Analysis** | 4 | Mass properties, simulation, validation |
| **Export** | 7 | Multi-format export and conversion |
| **Automation** | 8 | Batch processing and workflows |
| **File Management** | 3 | File operations and organization |
| **VBA Generation** | 10 | Dynamic VBA code for complex operations |
| **Template Management** | 6 | Template creation and standardization |
| **Macro Recording** | 8 | Macro recording, optimization, and libraries |

## Architecture Overview

The SolidWorks MCP Server uses an intelligent adapter architecture that automatically routes operations between direct COM API calls and VBA macro generation based on complexity analysis:

```mermaid
flowchart TB
    Client["MCP Client"] --> Server["FastMCP Server"]
    Server --> Router["Intelligent Router"]
    Router --> Analyzer["Complexity Analyzer"]
    
    Analyzer -->|"Simple Operations"| COM["Direct COM API"]
    Analyzer -->|"Complex Operations"| VBA["VBA Generation"]
    
    COM --> SW["SolidWorks Application"]
    VBA --> SW
    
    Router --> CB["Circuit Breaker"]
    Router --> Pool["Connection Pool"]
```

## Getting Started

Ready to automate your SolidWorks workflows? Check out our comprehensive guides:

- [**Installation Guide**](getting-started/installation.md) - Set up your development environment
- [**Quick Start**](getting-started/quickstart.md) - Your first SolidWorks automation  
- [**VS Code MCP Setup**](getting-started/vscode-mcp-setup.md) - Connect VS Code and GitHub Copilot to this server
- [**Claude Code MCP Setup**](getting-started/claude-code-setup.md) - Connect Claude Code to this server
- [**Architecture Overview**](user-guide/architecture.md) - Understand the system design
- [**Tools Overview**](user-guide/tools-overview.md) - Explore all 90+ available tools

---

**Ready to get started?** → [Installation Guide](getting-started/installation.md)
