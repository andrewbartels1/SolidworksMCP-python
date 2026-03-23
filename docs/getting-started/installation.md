# Installation Guide

This page is beginner-focused and platform-specific.

## Core Rule

SolidWorks COM automation only runs on Windows.

- Windows host: required for real SolidWorks control.
- Linux/WSL/container: great for development, docs, tests, and remote-client usage.

## Choose Your Setup Path

1. Windows only: full local SolidWorks automation.
2. Linux/WSL only: mock-mode development and docs.
3. WSL/Linux + Windows host: remote control of SolidWorks from Linux/WSL.

## What You Need

- Python 3.11+
- One environment manager: `conda`, `mamba`, or `micromamba`
- `make` (recommended for Linux/WSL workflows)
- SolidWorks installed and opened at least once (Windows only)

## 1. Install Prerequisites

### Python and PATH

In PowerShell, verify your Python installation:

```powershell
python --version
pip --version
```

If `python` is not found, reinstall Python and enable "Add python.exe to PATH".

### Conda (Environment Manager)

Install Conda using one of these options:

- **Miniforge** (recommended, conda-forge default): <https://github.com/conda-forge/miniforge>
- **Miniconda** (official Anaconda): <https://www.anaconda.com/docs/getting-started/miniconda/install/windows-cli-install#powershell>

After installation, close and reopen PowerShell, then verify:

```powershell
conda --version
conda info
conda env list
```

If `conda` is not found, initialize PowerShell and restart:

```powershell
conda init powershell
```

### SolidWorks (Windows only)

1. Install SolidWorks and find a valid license. Maker details are available at [SolidWorks Makers](https://www.solidworks.com/solution/solidworks-makers).
2. Maker licenses are generally non-commercial/personal and commonly described as limited to $2,000 USD annual profit. Always verify the current official terms before use.
3. Launch SolidWorks once manually.
4. Keep this Windows machine as the host for real automation.

## 2. Clone the Repository

=== "Windows (PowerShell)"

	```powershell
	git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
	cd SolidworksMCP-python
	```

=== "Linux / WSL (bash)"

	```bash
	git clone https://github.com/andrewbartels1/SolidworksMCP-python.git
	cd SolidworksMCP-python
	```

## 3. Create Environment and Install Dependencies

### Option A: Windows (Conda + PowerShell)

```powershell
# Create environment
conda create -n solidworks_mcp python=3.11

# Activate environment
conda activate solidworks_mcp

# Install package and dependencies
pip install -e ".[dev,test,docs]"
```

If activation fails in a new PowerShell session, initialize conda first:

```powershell
conda init powershell
```

### Option B: Linux / WSL (Make)

```bash
make install
```

## 4. Run Tests

Tests default to mock mode.

=== "Windows (PowerShell)"

	```powershell
	pytest
	pytest --cov=solidworks_mcp
	```

=== "Linux / WSL (bash)"

	```bash
	make test
	```

## 5. Start the MCP Server

### Local stdio mode (default)

```powershell
python -m solidworks_mcp.server
```

### Mock mode (for testing without SolidWorks)

=== "Windows (PowerShell)"

	```powershell
	python -m solidworks_mcp.server --mock
	```

=== "Linux / WSL (bash)"

	```bash
	make run
	```

### Remote HTTP mode (for remote clients)

Run on the Windows host:

```powershell
python -m solidworks_mcp.server --mode remote --host 0.0.0.0 --port 8000
```

Remote clients can then connect to `http://<windows-host-ip>:8000`.

For Linux/WSL clients, continue running tests/docs locally while targeting the Windows host for real SolidWorks operations.

## 6. Verify SolidWorks Connectivity

Verify the COM bridge on Windows:

```powershell
python -c "import win32com.client; print('win32com OK')"
```

If this fails, ensure SolidWorks is installed and the pywin32 module is properly configured.

From Linux/WSL, verify the Windows host port is reachable:

```bash
python - <<'PY'
import socket
host, port = "<windows-host-ip>", 8000
s = socket.socket()
s.settimeout(3)
s.connect((host, port))
print(f"Connected to {host}:{port}")
s.close()
PY
```

## 7. Optional: .env Configuration

Create a `.env` file from `.env.example` and set values for your machine.

Useful environment variables:

- `SOLIDWORKS_MCP_DEPLOYMENT_MODE` (`local`, `remote`, `hybrid`)
- `SOLIDWORKS_MCP_HOST` (default `127.0.0.1`)
- `SOLIDWORKS_MCP_PORT` (default `8000`)
- `SOLIDWORKS_MCP_MOCK_SOLIDWORKS` (`true` or `false`)
- `SOLIDWORKS_MCP_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING`, `ERROR`)

## Troubleshooting

### Conda environment not found

Ensure conda is initialized and the environment is created:

```powershell
conda init powershell
conda create -n solidworks_mcp python=3.11
conda activate solidworks_mcp
```

### `make install` fails on Linux/WSL

- Confirm `make` is installed (`sudo apt install make` on Debian/Ubuntu).
- Confirm one of `conda`, `mamba`, or `micromamba` is on PATH.
- Re-run with shell init loaded, then run `make install` again.

### SolidWorks does not connect

- Ensure SolidWorks is installed and has been launched at least once.
- You must be on Windows with SolidWorks COM available.
- Re-run COM check: `python -c "import win32com.client"`. (should run without printing any errors)
- If pywin32 is not working, reinstall it: `pip install --force-reinstall pywin32`.

### Import errors or missing dependencies

Reinforce the full environment reinstall:

```powershell
conda env remove -n solidworks_mcp
conda create -n solidworks_mcp python=3.11
conda activate solidworks_mcp
pip install -e ".[dev,test,docs]"
```

### Linux/WSL cannot reach Windows host

- Start server on Windows with `--mode remote --host 0.0.0.0 --port 8000`.
- Confirm Windows firewall allows inbound traffic on port 8000.
- Use Windows host IP address instead of `localhost` when required by your network setup.
