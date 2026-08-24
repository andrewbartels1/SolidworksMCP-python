#!/usr/bin/env python3
"""Local SolidWorks MCP Server startup script.

This script provides easy local testing and development of the SolidWorks MCP server
with configurable security, deployment modes, and comprehensive logging.
"""

import argparse
import asyncio
import io
import json
import logging
import signal
import sys
import time
from pathlib import Path

from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.server import SolidWorksMCPServer
from solidworks_mcp.utils.logging import setup_logging

# Add src to path for development
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

# Fix Windows console encoding for Unicode emojis
# On Windows, sys.stdout uses cp1252 by default which can't encode emojis
# Reconfigure to use UTF-8 for all print statements
if sys.platform == "win32":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", line_buffering=True
        )
    if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", line_buffering=True
        )


def eprint(*args, **kwargs) -> None:  # noqa: ANN002, ANN003 - thin print() passthrough
    """Print to stderr instead of stdout.

    MCP stdio hosts (Claude Desktop, VS Code, LM Studio) treat this process'
    stdout as a pure JSON-RPC channel once the FastMCP stdio transport takes
    over. Any decorative/human-readable output written to stdout is invalid
    framing from the client's point of view and can cause it to tear down the
    connection. All banner/status text in this script must go to stderr.
    """
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)


def create_local_config(
    mock_mode: bool = True,
    security_level: str = "minimal",
    port: int = 8000,
    log_level: str = "INFO",
    solidworks_year: int | None = None,
) -> SolidWorksMCPConfig:
    """Create configuration for local development/testing.

    Args:
        mock_mode (bool): The mock mode value. Defaults to True.
        security_level (str): The security level value. Defaults to "minimal".
        port (int): The port value. Defaults to 8000.
        log_level (str): The log level value. Defaults to "INFO".
        solidworks_year (int | None): The solidworks year value. Defaults to None.

    Returns:
        SolidWorksMCPConfig: The result produced by the operation.
    """

    # Convert string security level to enum
    security_map = {
        "minimal": SecurityLevel.MINIMAL,
        "standard": SecurityLevel.STANDARD,
        "strict": SecurityLevel.STRICT,
    }

    security_enum = security_map.get(security_level.lower(), SecurityLevel.MINIMAL)
    adapter_type = AdapterType.MOCK if mock_mode else AdapterType.PYWIN32

    config = SolidWorksMCPConfig(
        deployment_mode=DeploymentMode.LOCAL,
        security_level=security_enum,
        adapter_type=adapter_type,
        mock_solidworks=mock_mode,
        log_level=log_level,
        host="127.0.0.1",
        port=port,
        worker_processes=1,
        solidworks_path="mock://solidworks" if mock_mode else "",
        max_retries=3,
        timeout_seconds=30.0,
        solidworks_year=solidworks_year,
        circuit_breaker_enabled=True,
        connection_pooling=True,
        max_connections=5,
        enable_cors=True,
        api_key_required=False,
        rate_limit_enabled=False,
        allowed_origins=["http://localhost:3000", "http://localhost:8080"],
        api_keys=[],
    )

    return config


async def test_server_health(port: int, timeout: float = 10.0) -> bool:
    """Test if server is responding to health checks.

    Args:
        port (int): The port value.
        timeout (float): Maximum time to wait in seconds. Defaults to 10.0.

    Returns:
        bool: True if test server health, otherwise False.
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.get(f"http://127.0.0.1:{port}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "healthy"
                return False
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        return False


async def demonstrate_tools(server: SolidWorksMCPServer) -> None:
    """Demonstrate available tools and their capabilities.

    Args:
        server (SolidWorksMCPServer): The server value.

    Returns:
        None: None.
    """
    eprint("\n" + "=" * 60)
    eprint("🛠️ AVAILABLE SOLIDWORKS MCP TOOLS")
    eprint("=" * 60)

    # Get tool registry
    tools = server.get_available_tools()

    # Group by category
    categories = {}
    for tool in tools:
        category = tool.get("category", "General")
        if category not in categories:
            categories[category] = []
        categories[category].append(tool)

    # Display tools by category
    for category, category_tools in sorted(categories.items()):
        eprint(f"\n📁 {category} ({len(category_tools)} tools)")
        eprint("-" * 40)

        for tool in category_tools[:5]:  # Show first 5 tools per category
            name = tool.get("name", "Unknown")
            description = tool.get("description", "No description")
            eprint(f"  🔧 {name}")
            eprint(f"     {description[:80]}...")

        if len(category_tools) > 5:
            eprint(f"     ... and {len(category_tools) - 5} more tools")

    eprint(f"\n📊 Total Tools Available: {len(tools)}")


async def run_example_workflow(server: SolidWorksMCPServer) -> None:
    """Run an example SolidWorks automation workflow.

    Args:
        server (SolidWorksMCPServer): The server value.

    Returns:
        None: None.
    """
    eprint("\n" + "=" * 60)
    eprint("🎬 EXAMPLE WORKFLOW DEMONSTRATION")
    eprint("=" * 60)

    try:
        # Example: Create a simple part
        eprint("\n1. Creating new part...")
        create_result = await server.call_tool(
            "create_part",
            {
                "template": "Part Template",
                "part_name": "Example Part",
                "units": "mm",
                "material": "Steel",
            },
        )
        eprint(f"   ✅ Part creation: {create_result.get('status', 'unknown')}")

        # Example: Add sketch
        eprint("\n2. Creating sketch...")
        sketch_result = await server.call_tool(
            "create_sketch", {"plane": "Front Plane", "sketch_name": "Base Sketch"}
        )
        eprint(f"   ✅ Sketch creation: {sketch_result.get('status', 'unknown')}")

        # Example: Add rectangle
        eprint("\n3. Adding rectangle...")
        rect_result = await server.call_tool(
            "sketch_rectangle",
            {"width": 50.0, "height": 30.0, "center_x": 0.0, "center_y": 0.0},
        )
        eprint(f"   ✅ Rectangle creation: {rect_result.get('status', 'unknown')}")

        # Example: Create extrusion
        eprint("\n4. Creating extrusion...")
        extrude_result = await server.call_tool(
            "create_extrusion",
            {"sketch_name": "Base Sketch", "depth": 25.0, "direction": "Blind"},
        )
        eprint(f"   ✅ Extrusion: {extrude_result.get('status', 'unknown')}")

        eprint("\n🎉 Example workflow completed successfully!")

    except Exception as e:
        eprint(f"❌ Example workflow failed: {e}")


def setup_signal_handlers(server: SolidWorksMCPServer) -> None:
    """Setup graceful shutdown signal handlers.

    Args:
        server (SolidWorksMCPServer): The server value.

    Returns:
        None: None.
    """

    def signal_handler(signum, frame):
        """Handle signal handler.

        Args:
            signum (Any): The signum value.
            frame (Any): The frame value.

        Returns:
            Any: The result produced by the operation.
        """

        eprint(f"\n🛑 Received signal {signum}, shutting down gracefully...")
        asyncio.create_task(server.stop())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def print_startup_banner(config: SolidWorksMCPConfig) -> None:
    """Print startup banner with configuration info.

    Args:
        config (SolidWorksMCPConfig): Configuration values for the operation.

    Returns:
        None: None.
    """
    eprint("\n" + "=" * 60)
    eprint("🚀 SOLIDWORKS MCP SERVER - LOCAL DEVELOPMENT")
    eprint("=" * 60)
    eprint(f"📡 Server URL: http://{config.host}:{config.port}")
    eprint(f"🔒 Security Level: {config.security_level.value}")
    eprint(f"🎭 Adapter Mode: {'Mock' if config.mock_solidworks else 'Real SolidWorks'}")
    eprint(f"📊 Log Level: {config.log_level}")
    if getattr(config, "solidworks_year", None):
        eprint(f"📅 SolidWorks Year: {config.solidworks_year}")
    eprint(f"⏰ Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    eprint("=" * 60)


def print_connection_info(config: SolidWorksMCPConfig) -> None:
    """Print connection information for Claude Desktop.

    Args:
        config (SolidWorksMCPConfig): Configuration values for the operation.

    Returns:
        None: None.
    """
    eprint("\n" + "=" * 60)
    eprint("🔌 CLAUDE DESKTOP CONFIGURATION")
    eprint("=" * 60)

    run_mcp_script = project_root / "run-mcp.ps1"
    claude_config = {
        "mcpServers": {
            "solidworks": {
                "command": "powershell",
                "args": [
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(run_mcp_script),
                    "--mock" if config.mock_solidworks else "--real",
                    "--year",
                    str(config.solidworks_year) if config.solidworks_year else "2026",
                ],
            }
        }
    }

    eprint("Add this to your Claude Desktop config file:")
    eprint(json.dumps(claude_config, indent=2))

    config_locations = {
        "Windows (classic install)": "%APPDATA%\\Claude\\claude_desktop_config.json",
        "Windows (packaged install)": (
            "%LOCALAPPDATA%\\Packages\\Claude_<hash>\\LocalCache\\Roaming\\Claude\\"
            "claude_desktop_config.json"
        ),
        "macOS": "~/Library/Application Support/Claude/claude_desktop_config.json",
        "Linux": "~/.config/Claude/claude_desktop_config.json",
    }

    eprint("\nConfig file locations:")
    for os_name, path in config_locations.items():
        eprint(f"  {os_name}: {path}")


async def main():
    """Main server startup and management.

    Returns:
        Any: The result produced by the operation.
    """
    parser = argparse.ArgumentParser(
        description="SolidWorks MCP Server - Local Development"
    )

    # Configuration options
    parser.add_argument(
        "--mock", action="store_true", help="Use mock SolidWorks adapter (default)"
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Use real SolidWorks adapter (requires Windows + SolidWorks)",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Server port (default: 8000)"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="SolidWorks year hint (e.g., 2026, 2025)",
    )
    parser.add_argument(
        "--security",
        choices=["minimal", "standard", "strict"],
        default="minimal",
        help="Security level (default: minimal)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--no-demo", action="store_true", help="Skip demonstration workflow"
    )
    parser.add_argument(
        "--config-only", action="store_true", help="Only show configuration and exit"
    )

    args = parser.parse_args()

    # Determine mock mode
    mock_mode = not args.real  # Default to mock unless --real specified

    # Create configuration
    config = create_local_config(
        mock_mode=mock_mode,
        security_level=args.security,
        port=args.port,
        log_level=args.log_level,
        solidworks_year=args.year,
    )

    # Setup logging
    setup_logging(config)
    logger = logging.getLogger(__name__)

    print_startup_banner(config)
    print_connection_info(config)

    if args.config_only:
        eprint("\n✅ Configuration displayed. Use --help for startup options.")
        return

    server: SolidWorksMCPServer | None = None
    try:
        # Create and start server
        server = SolidWorksMCPServer(config)
        setup_signal_handlers(server)

        logger.info("Initializing server...")
        await server.setup()

        logger.info(
            f"Starting server (deployment_mode={config.deployment_mode.value})..."
        )
        # NOTE: for DeploymentMode.LOCAL (the only mode this script's config uses,
        # see create_local_config()) this call blocks for the entire lifetime of
        # the MCP stdio session - it only returns once the client disconnects.
        # Nothing below this line may touch stdout: the MCP host (Claude Desktop,
        # VS Code, LM Studio) treats stdout as a pure JSON-RPC channel while the
        # stdio transport is live, and stdio_server() closes the wrapped stdout
        # stream once the session ends, so a bare print() here raises
        # "ValueError: I/O operation on closed file" and crashes the process.
        await server.start()

        if config.deployment_mode == DeploymentMode.LOCAL:
            logger.info("MCP stdio session ended")
        else:
            # Remote/HTTP mode: start() returns as soon as the HTTP server is
            # bound, so it's safe to poll readiness and run the demo workflow.
            logger.info("Checking server health...")
            health_ok = await test_server_health(config.port)

            if health_ok:
                logger.info("Server is healthy and ready")
                await demonstrate_tools(server)

                if not args.no_demo:
                    await run_example_workflow(server)

                eprint(f"\n📡 Server running at http://{config.host}:{config.port}")
                eprint(f"📊 Health check: http://{config.host}:{config.port}/health")
                eprint(f"📖 API docs: http://{config.host}:{config.port}/docs")
                eprint("\n💡 Press Ctrl+C to stop the server")

                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    logger.info("Shutting down server...")
            else:
                logger.error("Server health check failed")

    except Exception as e:
        logger.error(f"Server startup failed: {e}")
        sys.exit(1)

    finally:
        if server is not None:
            try:
                await server.stop()
                logger.info("Server stopped gracefully")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")


if __name__ == "__main__":
    if sys.platform == "win32":
        # Use ProactorEventLoop for Windows compatibility (modern approach)
        # set_event_loop_policy is deprecated in Python 3.14+
        # Instead, we let asyncio.run() handle the policy automatically,
        # or we can explicitly create a Runner with the policy (3.11+)
        try:
            # Try the modern approach first (Python 3.11+)
            from asyncio import Runner

            runner = Runner(debug=False)
            try:
                runner.run(main())
            finally:
                runner.close()
        except (ImportError, TypeError):
            # Fallback for older versions
            asyncio.run(main())
    else:
        asyncio.run(main())
