# Typer CLI setup
import typer
import asyncio
from loguru import logger
from .config import DeploymentMode, load_config
from . import utils

app = typer.Typer(
    name="solidworks-mcp",
    help="SolidWorks MCP Server - Model Context Protocol for SolidWorks automation",
    no_args_is_help=True,
)


@app.command()
def run(
    config: str = typer.Option(
        None,
        "--config",
        help="Configuration file path",
        show_default=False,
    ),
    mode: str = typer.Option(
        None,
        "--mode",
        help="Deployment mode (local/remote/hybrid)",
        show_default=False,
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
    """Start the SolidWorks MCP Server."""
    # Load configuration
    loaded_config = load_config(config)

    # Override config with command-line arguments
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

    # Setup logging
    utils.setup_logging(loaded_config)

    logger.info("Starting SolidWorks MCP Server...")
    import platform
    import sys

    logger.info(f"Platform: {platform.system()}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Deployment mode: {loaded_config.deployment_mode}")
    logger.info(f"Security level: {loaded_config.security_level}")

    # Create and start server
    from .server import SolidWorksMCPServer

    server = SolidWorksMCPServer(loaded_config)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        asyncio.run(server.stop())


if __name__ == "__main__":
    app()
