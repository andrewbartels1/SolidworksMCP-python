#!/usr/bin/env python3
"""MCP stdio entrypoint for Claude Desktop, Claude Code, VS Code, and LM Studio.

Unlike start_local_server.py (a local dev/demo harness with decorative
startup banners and an HTTP health-check/demo-workflow path), this script
does nothing but start the SolidWorks MCP server over stdio. MCP hosts spawn
servers over raw stdio pipes and treat the child's stdout as a pure JSON-RPC
channel from the moment they spawn the process, so this script writes
nothing to stdout at all - all status output goes through the logger, which
is stderr-bound.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from solidworks_mcp.config import (
    AdapterType,
    DeploymentMode,
    SecurityLevel,
    SolidWorksMCPConfig,
)
from solidworks_mcp.server import SolidWorksMCPServer
from solidworks_mcp.utils.logging import setup_logging

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))


def _build_config(args: argparse.Namespace) -> SolidWorksMCPConfig:
    """Build the server config from parsed CLI args.

    Args:
        args (argparse.Namespace): Parsed command-line arguments.

    Returns:
        SolidWorksMCPConfig: The resulting configuration.
    """
    security_map = {
        "minimal": SecurityLevel.MINIMAL,
        "standard": SecurityLevel.STANDARD,
        "strict": SecurityLevel.STRICT,
    }
    mock_mode = not args.real

    return SolidWorksMCPConfig(
        deployment_mode=DeploymentMode.LOCAL,
        security_level=security_map.get(args.security, SecurityLevel.MINIMAL),
        adapter_type=AdapterType.MOCK if mock_mode else AdapterType.PYWIN32,
        mock_solidworks=mock_mode,
        log_level=args.log_level,
        host="127.0.0.1",
        port=args.port,
        worker_processes=1,
        solidworks_path="mock://solidworks" if mock_mode else "",
        max_retries=3,
        timeout_seconds=30.0,
        solidworks_year=args.year,
        circuit_breaker_enabled=True,
        connection_pooling=True,
        max_connections=5,
        enable_cors=True,
        api_key_required=False,
        rate_limit_enabled=False,
        allowed_origins=["http://localhost:3000", "http://localhost:8080"],
        api_keys=[],
    )


async def main() -> None:
    """Parse args, run the MCP stdio session, and exit cleanly.

    Returns:
        None: None.
    """
    parser = argparse.ArgumentParser(
        description="SolidWorks MCP stdio server (for MCP host configs)"
    )
    parser.add_argument(
        "--mock", action="store_true", help="Use mock SolidWorks adapter (default)"
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Use real SolidWorks adapter (requires Windows + SolidWorks)",
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Reserved for remote mode; unused over stdio"
    )
    parser.add_argument(
        "--year", type=int, default=None, help="SolidWorks year hint (e.g., 2026, 2025)"
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
    args = parser.parse_args()

    config = _build_config(args)
    setup_logging(config)
    logger = logging.getLogger(__name__)

    server = SolidWorksMCPServer(config)
    try:
        await server.setup()
        logger.info("Starting MCP stdio session...")
        # Blocks for the entire stdio session lifetime; only returns once
        # the client disconnects.
        await server.start()
        logger.info("MCP stdio session ended")
    finally:
        await server.stop()


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            from asyncio import Runner

            runner = Runner(debug=False)
            try:
                runner.run(main())
            finally:
                runner.close()
        except (ImportError, TypeError):
            asyncio.run(main())
    else:
        asyncio.run(main())
