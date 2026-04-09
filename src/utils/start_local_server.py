#!/usr/bin/env python3
"""
Local SolidWorks MCP Server startup script.

This script provides easy local testing and development of the SolidWorks MCP server
with configurable security, deployment modes, and comprehensive logging.
"""

import argparse
import asyncio
import io
import json
import logging
import os
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


def create_local_config(
    mock_mode: bool = True,
    security_level: str = "minimal",
    port: int = 8000,
    log_level: str = "INFO",
    solidworks_year: int | None = None,
) -> SolidWorksMCPConfig:
    """Create configuration for local development/testing."""

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
    """Test if server is responding to health checks."""
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
    """Demonstrate available tools and their capabilities."""
    print("\n" + "=" * 60)
    print("🛠️ AVAILABLE SOLIDWORKS MCP TOOLS")
    print("=" * 60)

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
        print(f"\n📁 {category} ({len(category_tools)} tools)")
        print("-" * 40)

        for tool in category_tools[:5]:  # Show first 5 tools per category
            name = tool.get("name", "Unknown")
            description = tool.get("description", "No description")
            print(f"  🔧 {name}")
            print(f"     {description[:80]}...")

        if len(category_tools) > 5:
            print(f"     ... and {len(category_tools) - 5} more tools")

    print(f"\n📊 Total Tools Available: {len(tools)}")


async def run_example_workflow(server: SolidWorksMCPServer) -> None:
    """Run an example SolidWorks automation workflow."""
    print("\n" + "=" * 60)
    print("🎬 EXAMPLE WORKFLOW DEMONSTRATION")
    print("=" * 60)

    try:
        # Example: Create a simple part
        print("\n1. Creating new part...")
        create_result = await server.call_tool(
            "create_part",
            {
                "template": "Part Template",
                "part_name": "Example Part",
                "units": "mm",
                "material": "Steel",
            },
        )
        print(f"   ✅ Part creation: {create_result.get('status', 'unknown')}")

        # Example: Add sketch
        print("\n2. Creating sketch...")
        sketch_result = await server.call_tool(
            "create_sketch", {"plane": "Front Plane", "sketch_name": "Base Sketch"}
        )
        print(f"   ✅ Sketch creation: {sketch_result.get('status', 'unknown')}")

        # Example: Add rectangle
        print("\n3. Adding rectangle...")
        rect_result = await server.call_tool(
            "sketch_rectangle",
            {"width": 50.0, "height": 30.0, "center_x": 0.0, "center_y": 0.0},
        )
        print(f"   ✅ Rectangle creation: {rect_result.get('status', 'unknown')}")

        # Example: Create extrusion
        print("\n4. Creating extrusion...")
        extrude_result = await server.call_tool(
            "create_extrusion",
            {"sketch_name": "Base Sketch", "depth": 25.0, "direction": "Blind"},
        )
        print(f"   ✅ Extrusion: {extrude_result.get('status', 'unknown')}")

        print("\n🎉 Example workflow completed successfully!")

    except Exception as e:
        print(f"❌ Example workflow failed: {e}")


def setup_signal_handlers(server: SolidWorksMCPServer) -> None:
    """Setup graceful shutdown signal handlers."""

    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
        asyncio.create_task(server.stop())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def print_startup_banner(config: SolidWorksMCPConfig) -> None:
    """Print startup banner with configuration info."""
    print("\n" + "=" * 60)
    print("🚀 SOLIDWORKS MCP SERVER - LOCAL DEVELOPMENT")
    print("=" * 60)
    print(f"📡 Server URL: http://{config.host}:{config.port}")
    print(f"🔒 Security Level: {config.security_level.value}")
    print(f"🎭 Adapter Mode: {'Mock' if config.mock_solidworks else 'Real SolidWorks'}")
    print(f"📊 Log Level: {config.log_level}")
    if getattr(config, "solidworks_year", None):
        print(f"📅 SolidWorks Year: {config.solidworks_year}")
    print(f"⏰ Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


def print_connection_info(config: SolidWorksMCPConfig) -> None:
    """Print connection information for Claude Desktop."""
    print("\n" + "=" * 60)
    print("🔌 CLAUDE DESKTOP CONFIGURATION")
    print("=" * 60)

    claude_config = {
        "mcpServers": {
            "solidworks": {
                "command": "python",
                "args": [
                    str(project_root / "src" / "utils" / "start_local_server.py"),
                    "--mock" if config.mock_solidworks else "--real",
                    f"--port={config.port}",
                    f"--security={config.security_level.value}",
                ],
            }
        }
    }

    print("Add this to your Claude Desktop config file:")
    print(json.dumps(claude_config, indent=2))

    config_locations = {
        "Windows": "%APPDATA%\\Claude\\claude_desktop_config.json",
        "macOS": "~/Library/Application Support/Claude/claude_desktop_config.json",
        "Linux": "~/.config/Claude/claude_desktop_config.json",
    }

    print(f"\nConfig file locations:")
    for os_name, path in config_locations.items():
        print(f"  {os_name}: {path}")


async def main():
    """Main server startup and management."""
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
        print("\n✅ Configuration displayed. Use --help for startup options.")
        return

    try:
        # Create and start server
        server = SolidWorksMCPServer(config)
        setup_signal_handlers(server)

        print(f"\n🔧 Initializing server...")
        await server.setup()

        print(f"🚀 Starting server on port {config.port}...")
        await server.start()

        # Wait for server to be ready
        print(f"🔍 Checking server health...")
        health_ok = await test_server_health(config.port)

        if health_ok:
            print(f"✅ Server is healthy and ready!")

            # Show available tools
            await demonstrate_tools(server)

            # Run example workflow if not disabled
            if not args.no_demo:
                await run_example_workflow(server)

            print(f"\n📡 Server running at http://{config.host}:{config.port}")
            print(f"📊 Health check: http://{config.host}:{config.port}/health")
            print(f"📖 API docs: http://{config.host}:{config.port}/docs")
            print(f"\n💡 Press Ctrl+C to stop the server")

            # Keep server running
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print(f"\n🛑 Shutting down server...")
        else:
            print(f"❌ Server health check failed")

    except Exception as e:
        logger.error(f"Server startup failed: {e}")
        print(f"❌ Server failed to start: {e}")
        sys.exit(1)

    finally:
        try:
            await server.stop()
            print(f"✅ Server stopped gracefully")
        except Exception as e:
            print(f"⚠️ Error during shutdown: {e}")


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
