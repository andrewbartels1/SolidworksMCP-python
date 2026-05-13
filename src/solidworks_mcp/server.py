"""Main SolidWorks MCP Server implementation using FastMCP and PydanticAI.

This server provides 88+ tools for comprehensive SolidWorks automation with configurable
deployment (local/remote) and security options.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import platform
import sys
import uuid
from pathlib import Path
from typing import Any

import typer
from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.toolsets.fastmcp import FastMCPToolset

from . import adapters, security, tools, utils
from .adapters.base import AdapterResult
from .adapters.complexity_analyzer import ComplexityAnalyzer
from .adapters.intelligent_router import IntelligentRouter
from .adapters.vba_adapter import VbaGeneratorAdapter
from .agents.history_db import insert_tool_event
from .cache.response_cache import CachePolicy, ResponseCache
from .config import DeploymentMode, SolidWorksMCPConfig, load_config
from .exceptions import SolidWorksMCPError

AGENT_SYSTEM_PROMPT = (
    "You are a SolidWorks automation expert. You have access to comprehensive "
    "SolidWorks tools for CAD automation, modeling, drawing creation, analysis, "
    "and file management. Always prioritize safety, accuracy, and user intent. "
    "For complex operations, break them down into manageable steps."
)


class MCPServerState(BaseModel):
    """Server state management - serializable fields only.

    Attributes:
        adapter (Any | None): The adapter value.
        agent (Any | None): The agent value.
        config (SolidWorksMCPConfig): The config value.
        is_connected (bool): The is connected value.
        startup_time (str | None): The startup time value.
        tool_count (int): The tool count value.
    """

    config: SolidWorksMCPConfig
    adapter: Any | None = None
    agent: Any | None = None
    is_connected: bool = False
    startup_time: str | None = None
    tool_count: int = 0


class SolidWorksMCPServer:
    """Main SolidWorks MCP Server class.

    Args:
        config (SolidWorksMCPConfig): Configuration values for the operation.

    Attributes:
        _db_logging_enabled (Any): The db logging enabled value.
        _db_path (Any): The db path value.
        _db_run_id (Any): The db run id value.
        _setup_complete (Any): The setup complete value.
        config (Any): The config value.
        mcp (Any): The mcp value.
        server (Any): The server value.
        state (Any): The state value.
    """

    def __init__(self, config: SolidWorksMCPConfig):
        """Initialize the solid works mcpserver.

        Args:
            config (SolidWorksMCPConfig): Configuration values for the operation.
        """
        self.config = config
        self.state = MCPServerState(config=config)
        self.mcp = FastMCP("SolidWorks MCP Server")
        self.server = None
        self._setup_complete = False
        self._db_logging_enabled = self._env_truthy(
            os.getenv("SOLIDWORKS_MCP_DB_LOGGING", "0")
        )
        self._db_run_id = os.getenv("SOLIDWORKS_MCP_CONVERSATION_ID") or str(
            uuid.uuid4()
        )
        self._db_path = (
            os.getenv("SOLIDWORKS_MCP_DB_PATH")
            if os.getenv("SOLIDWORKS_MCP_DB_PATH")
            else None
        )

        # Runtime objects (not serializable)
        self.adapter: Any | None = None
        self.agent: Any | None = None
        self._router: IntelligentRouter | None = None
        self._vba_adapter: VbaGeneratorAdapter | None = None

    @staticmethod
    def _env_truthy(value: str | None) -> bool:
        """Build internal env truthy.

        Args:
            value (str | None): The value value.

        Returns:
            bool: True if env truthy, otherwise False.
        """

        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    def _log_tool_event(
        self,
        *,
        tool_name: str,
        phase: str,
        payload: dict[str, Any] | None,
    ) -> None:
        """Build internal log tool event.

        Args:
            tool_name (str): The tool name value.
            phase (str): The phase value.
            payload (dict[str, Any] | None): The payload value.

        Returns:
            None: None.
        """

        if not self._db_logging_enabled:
            return
        try:
            insert_tool_event(
                run_id=self._db_run_id,
                tool_name=tool_name,
                phase=phase,
                payload_json=json.dumps(payload, ensure_ascii=True)
                if payload is not None
                else None,
                db_path=(
                    Path(os.path.abspath(self._db_path))
                    if isinstance(self._db_path, str)
                    else None
                ),
            )
        except Exception as exc:  # pragma: no cover
            logger.debug("Tool event logging skipped due to error: {}", exc)

    def _configure_runtime_services(self) -> None:
        """Initialize router and cache services and instrument adapter methods.

        Returns:
            None: None.
        """
        if self.adapter is None:
            return

        analyzer = ComplexityAnalyzer(
            parameter_threshold=self.config.complexity_parameter_threshold,
            score_threshold=self.config.complexity_score_threshold,
        )
        cache = ResponseCache(
            CachePolicy(
                enabled=self.config.enable_response_cache,
                default_ttl_seconds=self.config.response_cache_ttl_seconds,
                max_entries=self.config.response_cache_max_entries,
            )
        )
        self._router = IntelligentRouter(analyzer=analyzer, cache=cache)
        self._vba_adapter = VbaGeneratorAdapter(backing_adapter=self.adapter)

        if self.config.enable_intelligent_routing:
            self._instrument_adapter_methods()

    def _instrument_adapter_methods(self) -> None:
        """Route selected adapter methods through intelligent router.

        Returns:
            None: None.
        """
        if self.adapter is None or self._router is None:
            return

        routed_operations = {
            "create_extrusion",
            "create_revolve",
            "create_sweep",
            "create_loft",
            "get_model_info",
            "list_features",
            "list_configurations",
            "get_mass_properties",
            # Additional analysis operations
            "calculate_mass_properties",
            "get_material_properties",
            "analyze_geometry",
            "check_interference",
            # Drawing analysis operations
            "analyze_drawing_comprehensive",
            "analyze_drawing_dimensions",
            "analyze_drawing_views",
            "analyze_drawing_annotations",
            "check_drawing_compliance",
            "check_drawing_standards",
            "compare_drawing_versions",
            # Modeling operations that benefit from routing
            "create_assembly",
            "create_part",
            "create_drawing",
            "insert_component",
            "add_mate",
            # Sketching operations
            "create_sketch",
            "add_circle",
            "add_rectangle",
            "add_line",
            "add_arc",
            "add_spline",
            "add_polygon",
            "add_sketch_constraint",
            "add_sketch_dimension",
            # Drawing operations
            "create_drawing_view",
            "add_drawing_annotation",
            "add_dimension",
            # File and metadata operations
            "get_file_properties",
            "get_dimension",
            "classify_feature_tree",
            "discover_solidworks_docs",
        }

        for operation_name in routed_operations:
            original_operation = getattr(self.adapter, operation_name, None)
            if original_operation is None or not callable(original_operation):
                continue

            vba_operation = None
            if self._vba_adapter is not None:
                candidate = getattr(self._vba_adapter, operation_name, None)
                if callable(candidate):
                    vba_operation = candidate

            async def _routed_call(
                *call_args: Any,
                _operation_name: str = operation_name,
                _com_callable: Any = original_operation,
                _vba_callable: Any = vba_operation,
                **call_kwargs: Any,
            ) -> AdapterResult[Any]:
                """Build internal routed call.

                Args:
                    *call_args (Any): Additional positional arguments forwarded to the call.
                    _operation_name (str): The operation name value. Defaults to operation_name.
                    _com_callable (Any): The com callable value. Defaults to original_operation.
                    _vba_callable (Any): The vba callable value. Defaults to vba_operation.
                    **call_kwargs (Any): Additional keyword arguments forwarded to the call.

                Returns:
                    AdapterResult[Any]: The result produced by the operation.
                """
                payload: Any
                if call_kwargs:
                    payload = {
                        "args": call_args,
                        "kwargs": call_kwargs,
                    }
                elif len(call_args) == 1:
                    payload = call_args[0]
                elif call_args:
                    payload = {"args": call_args}
                else:
                    payload = None

                if self._router is None:
                    return await _com_callable(*call_args, **call_kwargs)

                result, _ = await self._router.execute(
                    operation=_operation_name,
                    payload=payload,
                    call_args=call_args,
                    call_kwargs=call_kwargs,
                    com_operation=_com_callable,
                    vba_operation=_vba_callable,
                    cache_ttl_seconds=self.config.response_cache_ttl_seconds,
                )
                return result

            setattr(self.adapter, operation_name, _routed_call)

    async def setup(self) -> None:
        """Initialize the server components.

        Returns:
            None: None.
        """
        if self._setup_complete:
            return

        logger.info("Setting up SolidWorks MCP Server...")

        # Validate environment
        await utils.validate_environment(self.config)

        # Setup security
        await security.setup_security(self.mcp, self.config)

        # Create SolidWorks adapter
        self.adapter = await adapters.create_adapter(self.config)
        self._configure_runtime_services()
        self.state.adapter = self.adapter

        # Register tools and derive canonical count from FastMCP runtime
        await tools.register_tools(self.mcp, self.adapter, self.config)
        self.state.tool_count = len(await self.mcp.list_tools())
        self.server = self.mcp

        # Setup PydanticAI agent after tools are registered so the agent can bind
        # directly to the in-process FastMCP server without a transport hop.
        await self._setup_agent()
        self.state.agent = self.agent

        self._setup_complete = True
        logger.info(f"Server setup complete with {self.state.tool_count} tools")

    async def _setup_agent(self) -> None:
        """Setup PydanticAI agent for enhanced LLM integration.

        Returns:
            None: None.
        """
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
        """Start local MCP stdio transport using the available FastMCP API.

        Returns:
            None: None.

        Raises:
            SolidWorksMCPError: FastMCP server does not expose a stdio runner.
        """
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
        """Start the MCP server.

        Returns:
            None: None.
        """
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
        """Start HTTP server for remote access.

        Returns:
            None: None.
        """
        run_result = self.mcp.run(
            transport="http", host=self.config.host, port=self.config.port
        )
        if inspect.isawaitable(run_result):
            await run_result

    async def stop(self) -> None:
        """Gracefully stop the server.

        Returns:
            None: None.
        """
        logger.info("Stopping SolidWorks MCP Server...")

        if self.adapter:
            await self.adapter.disconnect()
            self.state.is_connected = False

        self._setup_complete = False
        self.server = None
        logger.info("Server stopped")

    async def health_check(self) -> dict[str, Any]:
        """Get server health status.

        Returns:
            dict[str, Any]: A dictionary containing the resulting values.
        """
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
    """Get comprehensive server status information.

    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    # This will be properly implemented when the server instance is available
    return {
        "status": "Server status endpoint - to be implemented with server state",
        "message": "Use the main server health_check method for detailed status",
    }


async def list_capabilities() -> dict[str, list[str]]:
    """List all available SolidWorks capabilities and tool categories.

    Returns:
        dict[str, list[str]]: A dictionary containing the resulting values.
    """
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
    """Create a SolidWorks MCP Server instance.

    Args:
        config (SolidWorksMCPConfig | None): Configuration values for the operation.
                                             Defaults to None.

    Returns:
        SolidWorksMCPServer: The result produced by the operation.
    """
    if config is None:
        config = load_config()

    return SolidWorksMCPServer(config)


async def _run_server(server: SolidWorksMCPServer) -> None:
    """Run server lifecycle with graceful shutdown.

    Args:
        server (SolidWorksMCPServer): The server value.

    Returns:
        None: None.
    """
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        await server.stop()


async def _run_with_config(config: SolidWorksMCPConfig) -> None:
    """Run the server from a fully prepared config object.

    Args:
        config (SolidWorksMCPConfig): Configuration values for the operation.

    Returns:
        None: None.
    """
    utils.setup_logging(config)

    logger.info("Starting SolidWorks MCP Server...")
    logger.info(f"Platform: {platform.system()}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Deployment mode: {config.deployment_mode}")
    logger.info(f"Security level: {config.security_level}")

    server = SolidWorksMCPServer(config)
    await _run_server(server)


def cli(
    config: str | None = typer.Option(
        None,
        "--config",
        help="Configuration file path",
    ),
    mode: str | None = typer.Option(
        None,
        "--mode",
        help="Deployment mode (local/remote/hybrid)",
    ),
    host: str = typer.Option(
        "localhost",
        "--host",
        help="Server host for remote mode",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        help="Server port for remote mode",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug mode",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Use mock SolidWorks for testing",
    ),
) -> None:
    """Start the SolidWorks MCP Server.

    Args:
        config (str | None): Configuration values for the operation. Defaults to
                             typer.Option(         None,         "--config",
                             help="Configuration file path",     ).
        mode (str | None): The mode value. Defaults to typer.Option(         None,         "
                           --mode",         help="Deployment mode (local/remote/hybrid)",
                           ).
        host (str): The host value. Defaults to typer.Option(         "localhost",         "
                    --host",         help="Server host for remote mode",     ).
        port (int): The port value. Defaults to typer.Option(         8000,         "--
                    port",         help="Server port for remote mode",     ).
        debug (bool): The debug value. Defaults to typer.Option(         False,         "--
                      debug",         help="Enable debug mode",     ).
        mock (bool): The mock value. Defaults to typer.Option(         False,         "--
                     mock",         help="Use mock SolidWorks for testing",     ).

    Returns:
        None: None.
    """
    loaded_config = load_config(config)

    if mode:
        loaded_config.deployment_mode = DeploymentMode(mode)
    if host:
        loaded_config.host = host
    if port:
        loaded_config.port = port
    if debug:
        loaded_config.debug = True
        loaded_config.log_level = "DEBUG"
    if mock:
        loaded_config.mock_solidworks = True

    asyncio.run(_run_with_config(loaded_config))


async def main() -> None:
    """Legacy async entry point retained for tests and internal callers.

    Returns:
        None: None.
    """
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

    config = load_config(args.config)

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

    await _run_with_config(config)


def cli_main() -> None:
    """Console script entry point using Typer CLI.

    Returns:
        None: None.
    """
    typer.run(cli)


def run_server() -> None:
    """Synchronous entry point for the server.

    Returns:
        None: None.
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
