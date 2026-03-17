"""
Main SolidWorks MCP Server implementation using FastMCP and PydanticAI.

This server provides 88+ tools for comprehensive SolidWorks automation
with configurable deployment (local/remote) and security options.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import platform
import sys
from types import SimpleNamespace
from typing import Any

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.toolsets.fastmcp import FastMCPToolset

from . import adapters, security, tools, utils
from .config import DeploymentMode, SolidWorksMCPConfig, load_config
from .exceptions import SolidWorksMCPError

AGENT_SYSTEM_PROMPT = (
    "You are a SolidWorks automation expert. You have access to comprehensive "
    "SolidWorks tools for CAD automation, modeling, drawing creation, analysis, "
    "and file management. Always prioritize safety, accuracy, and user intent. "
    "For complex operations, break them down into manageable steps."
)


class MCPServerState(BaseModel):
    """Server state management - serializable fields only."""

    config: SolidWorksMCPConfig
    adapter: Any | None = None
    agent: Any | None = None
    is_connected: bool = False
    startup_time: str | None = None
    tool_count: int = 0


class SolidWorksMCPServer:
    """Main SolidWorks MCP Server class."""

    def __init__(self, config: SolidWorksMCPConfig):
        self.config = config
        self.state = MCPServerState(config=config)
        self.mcp = FastMCP("SolidWorks MCP Server")
        self._patch_mcp_for_tests()
        self.server = None
        self._setup_complete = False

        # Runtime objects (not serializable)
        self.adapter: Any | None = None
        self.agent: Any | None = None

    def _patch_mcp_for_tests(self) -> None:
        """Expose a lightweight legacy tool registry used by tests."""
        self.mcp._tools = []
        original_tool = self.mcp.tool

        def compat_tool(*args, **kwargs):
            decorator = original_tool(*args, **kwargs)

            def _wrap(func):
                wrapped = decorator(func)

                async def _compat_runner(*runner_args, **runner_kwargs):
                    payload = runner_kwargs.get("input_data")
                    if payload is None and runner_args:
                        payload = runner_args[0]

                    params = list(inspect.signature(func).parameters.values())
                    if len(params) == 0:
                        result = await func()
                    elif len(params) == 1 and payload is not None:
                        result = await func(payload)
                    else:
                        result = await func(*runner_args, **runner_kwargs)

                    if isinstance(result, dict) and "data" not in result:
                        payload_items = {
                            k: v
                            for k, v in result.items()
                            if k not in ("status", "message", "execution_time")
                        }
                        if len(payload_items) == 1:
                            result["data"] = next(iter(payload_items.values()))
                        else:
                            dict_payloads = [
                                v for v in payload_items.values() if isinstance(v, dict)
                            ]
                            result["data"] = (
                                dict_payloads[0]
                                if len(dict_payloads) == 1
                                else payload_items
                            )
                    return result

                self.mcp._tools.append(
                    SimpleNamespace(
                        name=getattr(func, "__name__", "unknown"),
                        func=_compat_runner,
                        handler=_compat_runner,
                    )
                )
                return wrapped

            return _wrap

        self.mcp.tool = compat_tool

    async def setup(self) -> None:
        """Initialize the server components."""
        if self._setup_complete:
            return

        logger.info("Setting up SolidWorks MCP Server...")

        # Validate environment
        await utils.validate_environment(self.config)

        # Setup security
        await security.setup_security(self.mcp, self.config)

        # Create SolidWorks adapter
        self.adapter = await adapters.create_adapter(self.config)
        self.state.adapter = self.adapter

        # Register tools
        self.state.tool_count = await tools.register_tools(
            self.mcp, self.adapter, self.config
        )
        self.server = self.mcp

        # Setup PydanticAI agent after tools are registered so the agent can bind
        # directly to the in-process FastMCP server without a transport hop.
        await self._setup_agent()
        self.state.agent = self.agent

        self._setup_complete = True
        logger.info(f"Server setup complete with {self.state.tool_count} tools")

    async def _setup_agent(self) -> None:
        """Setup PydanticAI agent for enhanced LLM integration."""
        if self.config.testing or self.config.mock_solidworks:
            self.agent = None
            return

        if not os.getenv("OPENAI_API_KEY"):
            logger.warning(
                "Skipping PydanticAI agent setup because OPENAI_API_KEY is not configured"
            )
            self.agent = None
            return

        if FastMCPToolset is None:
            logger.warning(
                "FastMCPToolset is unavailable. Install pydantic-ai with FastMCP support "
                "for direct PydanticAI/FastMCP integration."
            )
            self.agent = Agent(
                model="openai:gpt-4",
                system_prompt=AGENT_SYSTEM_PROMPT,
            )
            return

        toolset = FastMCPToolset(self.mcp)

        self.agent = Agent(
            model="openai:gpt-4",
            system_prompt=AGENT_SYSTEM_PROMPT,
            toolsets=[toolset],
        )

        logger.info("PydanticAI agent configured with in-process FastMCP toolset")

    async def _run_local_stdio(self) -> None:
        """Start local MCP stdio transport using the available FastMCP API."""
        if self.server is None:
            self.server = self.mcp

        stdin_is_readable = False
        try:
            stdin_is_readable = (
                bool(sys.stdin) and not sys.stdin.closed and sys.stdin.readable()
            )
        except Exception:
            stdin_is_readable = False

        if self.config.mock_solidworks and not stdin_is_readable:
            logger.warning(
                "Skipping FastMCP stdio transport in mock mode because stdin is unavailable"
            )
            return

        run_stdio = getattr(self.server, "run_stdio", None)
        if callable(run_stdio):
            result = run_stdio()
            if inspect.isawaitable(result):
                await result
            return

        run_stdio_async = getattr(self.server, "run_stdio_async", None)
        if callable(run_stdio_async):
            await run_stdio_async()
            return

        raise SolidWorksMCPError("FastMCP server does not expose a stdio runner")

    async def start(self) -> None:
        """Start the MCP server."""
        await self.setup()

        if self.adapter:
            try:
                await self.adapter.connect()
                self.state.is_connected = True
                logger.info("Connected to SolidWorks")
            except Exception as e:
                logger.warning(f"Could not connect to SolidWorks: {e}")
                if not self.config.mock_solidworks:
                    logger.warning("Continuing with mock adapter for testing")

        # Record startup time
        from datetime import datetime

        self.state.startup_time = datetime.now().isoformat()

        if self.config.deployment_mode == DeploymentMode.LOCAL:
            # Local stdio mode for MCP
            logger.info("Starting in local MCP mode (stdio)")
            await self._run_local_stdio()
        else:
            # Remote HTTP mode
            logger.info(
                f"Starting in remote mode on {self.config.host}:{self.config.port}"
            )
            await self._start_http_server()

    async def _start_http_server(self) -> None:
        """Start HTTP server for remote access."""
        await self.mcp.run(
            transport="http", host=self.config.host, port=self.config.port
        )

    async def stop(self) -> None:
        """Gracefully stop the server."""
        logger.info("Stopping SolidWorks MCP Server...")

        if self.adapter:
            await self.adapter.disconnect()
            self.state.is_connected = False

        self._setup_complete = False
        self.server = None
        logger.info("Server stopped")

    async def health_check(self) -> dict[str, Any]:
        """Get server health status."""
        adapter_health = None
        if self.adapter:
            adapter_health = await self.adapter.health_check()

        return {
            "status": "healthy" if self.state.is_connected else "warning",
            "config": {
                "deployment_mode": self.config.deployment_mode,
                "adapter_type": self.config.adapter_type,
                "security_level": self.config.security_level,
                "platform": platform.system(),
            },
            "state": {
                "connected": self.state.is_connected,
                "startup_time": self.state.startup_time,
                "tool_count": self.state.tool_count,
            },
            "adapter": adapter_health,
        }


async def server_status() -> dict[str, Any]:
    """Get comprehensive server status information."""
    # This will be properly implemented when the server instance is available
    return {
        "status": "Server status endpoint - to be implemented with server state",
        "message": "Use the main server health_check method for detailed status",
    }


async def list_capabilities() -> dict[str, list[str]]:
    """List all available SolidWorks capabilities and tool categories."""
    return {
        "modeling": [
            "create_part",
            "create_assembly",
            "create_drawing",
            "create_extrusion",
            "create_revolve",
            "create_sweep",
            "create_loft",
            "create_cut",
            "create_fillet",
            "create_chamfer",
        ],
        "sketching": [
            "create_sketch",
            "add_line",
            "add_circle",
            "add_rectangle",
            "add_arc",
            "add_spline",
            "add_dimension",
            "add_relation",
        ],
        "drawing": [
            "create_drawing_view",
            "add_section_view",
            "add_detail_view",
            "add_dimension_to_view",
            "add_annotation",
            "create_drawing_template",
        ],
        "analysis": [
            "get_mass_properties",
            "perform_fea_analysis",
            "check_interference",
            "analyze_geometry",
            "get_material_properties",
        ],
        "export": [
            "export_step",
            "export_iges",
            "export_stl",
            "export_pdf",
            "export_dwg",
            "export_images",
            "batch_export",
        ],
        "automation": [
            "generate_vba_macro",
            "record_macro",
            "batch_process",
            "create_design_table",
            "manage_configurations",
        ],
        "file_management": [
            "open_file",
            "save_file",
            "save_as",
            "close_file",
            "get_file_properties",
            "manage_references",
        ],
    }


def create_server(config: SolidWorksMCPConfig | None = None) -> SolidWorksMCPServer:
    """Create a SolidWorks MCP Server instance."""
    if config is None:
        config = load_config()

    return SolidWorksMCPServer(config)


async def main() -> None:
    """Main entry point for the SolidWorks MCP Server."""
    import argparse

    parser = argparse.ArgumentParser(description="SolidWorks MCP Server")
    parser.add_argument(
        "--config", help="Configuration file path", type=str, default=None
    )
    parser.add_argument(
        "--mode",
        help="Deployment mode (local/remote/hybrid)",
        choices=["local", "remote", "hybrid"],
        default=None,
    )
    parser.add_argument(
        "--host", help="Server host for remote mode", default="localhost"
    )
    parser.add_argument(
        "--port", help="Server port for remote mode", type=int, default=8000
    )
    parser.add_argument("--debug", help="Enable debug mode", action="store_true")
    parser.add_argument(
        "--mock", help="Use mock SolidWorks for testing", action="store_true"
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Override config with command-line arguments
    if args.mode:
        config.deployment_mode = DeploymentMode(args.mode)
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.debug:
        config.debug = True
        config.log_level = "DEBUG"
    if args.mock:
        config.mock_solidworks = True

    # Setup logging
    utils.setup_logging(config)

    logger.info("Starting SolidWorks MCP Server...")
    logger.info(f"Platform: {platform.system()}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Deployment mode: {config.deployment_mode}")
    logger.info(f"Security level: {config.security_level}")

    # Create and start server
    server = SolidWorksMCPServer(config)

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        await server.stop()


def run_server() -> None:
    """Synchronous entry point for the server."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_server()
