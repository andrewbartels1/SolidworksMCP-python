# Installation Guide

This guide will help you set up the SolidWorks MCP Server on your Windows machine.

## Prerequisites

## Beginner Setup: Windows 11 + Optional WSL

This project is easiest to understand with one rule:

- Windows runs SolidWorks and COM automation.
- WSL/Linux can be used for development and as a client to the Windows-hosted server.

## Official Downloads

1. Windows 11: <https://www.microsoft.com/windows/get-windows-11>
2. Python (Windows installer): <https://www.python.org/downloads/windows/>
3. WSL install guide: <https://learn.microsoft.com/windows/wsl/install>
4. Docker Desktop (Windows): <https://www.docker.com/products/docker-desktop/>
5. Docker Desktop WSL integration docs: <https://docs.docker.com/desktop/features/wsl/>
6. SolidWorks: <https://www.solidworks.com/support/downloads>

## Install Location Matrix

| Component | Install on Windows 11 | Install in WSL/Linux |
| --- | --- | --- |
| SolidWorks | Yes | No |
| pywin32 / COM runtime | Yes | No |
| Python runtime for MCP server | Yes | Optional |
| This repo + tests + lint | Optional | Yes (recommended) |
| Docker Desktop | Optional | No (Docker engine is provided via Docker Desktop integration) |

## Step-by-Step (Beginner Friendly)

### 1) Install Python on Windows and add to PATH

1. Download Python for Windows from the official link above.
2. In the installer, check "Add python.exe to PATH".
3. Open PowerShell and verify:

```powershell
python --version
pip --version
```

If this fails, reinstall Python and ensure PATH was enabled.

### 2) Install SolidWorks on Windows

1. Install your licensed SolidWorks version.
2. Start SolidWorks once manually to complete first-run setup.
3. Keep SolidWorks available on the same Windows machine that will run the MCP server.

### 3) (Optional) Install Docker Desktop on Windows

Docker is useful for docs/dev helper tooling, but SolidWorks COM automation itself must still run on Windows, not in a Linux container.

1. Install Docker Desktop from the official link.
2. Enable WSL integration in Docker Desktop settings.
3. Verify from PowerShell:

```powershell
docker --version
docker info
```

### 4) Install WSL (Optional but recommended for Linux-style development)

1. Install WSL from the official Microsoft link.
2. Open Ubuntu (or your chosen distro) and verify:

```bash
wsl --version
uname -a
```

### 5) Set up and run the MCP server on Windows

1. Open PowerShell in the repo folder (Windows path).
2. Run installation and activate environment.
3. Start server in remote mode so WSL/Linux clients can connect.

```powershell
make install
conda activate solidworks_mcp
python start_local_server.py --security-level standard --host 0.0.0.0 --port 8000
```

If you use mamba/micromamba, replace `conda activate` with your environment command.

### 6) Set up client/development environment in WSL

1. Clone repo inside WSL.
2. Install development dependencies.
3. Point your client/tools to the Windows-hosted server endpoint.

```bash
git clone https://github.com/yourusername/SolidworksMCP-python.git
cd SolidworksMCP-python
make install
```

Use `http://localhost:8000` first for WSL2 local-machine setups. If needed, use the Windows host LAN IP.

### 7) Verify Windows-host and WSL-client connectivity

Windows PowerShell check:

```powershell
python -c "from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter; print('pywin32 adapter import OK')"
```

WSL check:

```bash
python - <<'PY'
import socket
s = socket.socket()
s.settimeout(3)
s.connect(("localhost", 8000))
print("Connection to Windows-hosted MCP server is reachable")
s.close()
PY
```

If this fails, check Windows Firewall rules for the configured port.

### System Requirements

- **Operating System**: Windows 10/11 (SolidWorks COM requires Windows)

- **Python**: 3.12 or higher

- **SolidWorks**: 2020 or later

- **Memory**: 4GB RAM minimum, 8GB recommended

### Required Software

#### 1. Conda/Mamba (Recommended)

We recommend using mamba for faster package management:

```bash

# Install Miniforge (includes mamba)

curl -L -O \"https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh\"

bash Miniforge3-$(uname)-$(uname -m).sh

```

Or install Miniconda with mamba:

```bash

conda install mamba -n base -c conda-forge

```

#### 2. UV (Fast Python Package Manager)

UV is automatically installed in the conda environment, but you can install it globally:

```bash

# Windows

pip install uv



# Or with conda

conda install -c conda-forge uv

```

## Installation Steps

### Method 1: Automated Setup (Recommended)

1. **Clone the repository**:

   ```bash

   git clone https://github.com/yourusername/SolidworksMCP-python.git

   cd SolidworksMCP-python

   ```

2. **Run the automated installer**:

   ```bash

   make install

   ```

   This will:

   - Create a conda environment named `solidworks_mcp`

   - Install Python 3.12 and required dependencies

   - Set up the package in development mode

3. **Activate the environment and complete setup**:

   ```bash

   mamba activate solidworks_mcp

   uv pip install -e .[dev,test,docs]

   python -m ipykernel install --user --name solidworks_mcp --display-name \"Python (SolidWorks MCP)\"

   ```

### Method 2: Manual Setup

If you prefer manual installation or encounter issues:

1. **Create conda environment**:

   ```bash

   mamba env create -f solidworks_mcp.yml -y

   # Or with conda:

   conda env create -f solidworks_mcp.yml -y

   ```

2. **Activate environment**:

   ```bash

   mamba activate solidworks_mcp

   ```

3. **Install the package**:

   ```bash

   uv pip install -e .[dev,test,docs]

   ```

4. **Install Jupyter kernel** (optional):

   ```bash

   python -m ipykernel install --user --name solidworks_mcp --display-name \"Python (SolidWorks MCP)\"

   ```

## Verification

### 1. Test Installation

```bash

python -c \"import solidworks_mcp; print('Installation successful!')\"

```

### 2. Check Tool Count

```bash

python verify_tool_count.py

```

You should see:

```text

Total Tools: 90+

Status: ✓ TARGET ACHIEVED

```

### 3. Test SolidWorks Connection

```bash

python -c \"from solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter; print('COM adapter loaded successfully')\"

```

## Configuration

### 1. Create Configuration File

Create `config/local_config.json`:

```json

{

  \"solidworks\": {

    \"startup_timeout\": 30,

    \"operation_timeout\": 60,

    \"auto_connect\": true

  },

  \"security\": {

    \"level\": \"standard\",

    \"validate_files\": true,

    \"sandbox_mode\": false

  },

  \"logging\": {

    \"level\": \"INFO\",

    \"file\": \"logs/solidworks_mcp.log\"

  }

}

```

### 2. Environment Variables

Optional environment variables:

```bash

# Set in your shell profile or .env file

export SOLIDWORKS_MCP_CONFIG=\"config/local_config.json\"

export SOLIDWORKS_MCP_LOG_LEVEL=\"INFO\"

export USE_MOCK_SOLIDWORKS=\"false\"  # Set to true for testing without SolidWorks

```

## Troubleshooting

### Common Issues

#### 1. COM Registration Issues

If SolidWorks COM is not accessible:

```powershell

# Run as Administrator

regsvr32 \"C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\sldworks.tlb\"

```

#### 2. Python Path Issues

Ensure the conda environment is activated:

```bash

which python

# Should point to: ~/miniforge3/envs/solidworks_mcp/bin/python

```

#### 3. Permission Issues

Run Visual Studio Code or your IDE as Administrator when working with COM.

#### 4. Environment Conflicts

If you have multiple Python installations:

```bash

# Clean install

mamba env remove -n solidworks_mcp

mamba clean --all

# Then reinstall

```

## Development Setup

For development work:

```bash

# Install development tools

make install-dev



# Run tests

make test



# Check code quality

make check



# Format code

make format

```

## Documentation Roadmap (Planned)

> Under construction: visual beginner walkthroughs are being built.

We will add a dedicated beginner docs section with visuals so users can follow GUI + agent workflows without prior MCP experience.

Planned additions:

1. Step-by-step guides with screenshots for Windows install, WSL setup, and first connection.
2. Short demo videos showing agent-to-MCP-to-SolidWorks flow.
3. "First 10 minutes" examples from simple operations to multi-step automation.
4. Separate guides per tool: Claude Code, GitHub Copilot, and other code-first clients.
5. Troubleshooting decision trees for GUI+code mixed workflows.

## Next Steps

Once installed, proceed to:

- [Quick Start Guide](quickstart.md) - Your first automation
- [Architecture Overview](../user-guide/architecture.md) - Understand the system design  
- [Tools Overview](../user-guide/tools-overview.md) - Explore all available tools

---

**Need help?** Open an issue on GitHub for support and questions.
