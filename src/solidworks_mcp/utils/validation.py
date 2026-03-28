"""
Environment validation for SolidWorks MCP Server.
"""

import platform
import shutil
from loguru import logger
from ..config import SolidWorksMCPConfig
from ..exceptions import SolidWorksMCPError


async def validate_environment(config: SolidWorksMCPConfig) -> None:
    """Validate runtime prerequisites for the server.

    Args:
        config: Loaded server configuration.

    Raises:
        SolidWorksMCPError: If the active Python runtime is unsupported.
    """
    logger.info("Validating environment...")

    # Check platform
    if not config.can_use_solidworks and not config.mock_solidworks:
        if platform.system() != "Windows":
            logger.warning("SolidWorks requires Windows platform. Using mock adapter.")
        else:
            logger.warning("SolidWorks not available. Using mock adapter.")

    # Check SolidWorks installation if on Windows
    if (
        config.enable_windows_validation
        and platform.system() == "Windows"
        and not config.mock_solidworks
    ):
        await _validate_solidworks_installation(config)

    # Check Python version
    import sys

    python_version = sys.version_info
    if python_version < (3, 11):
        raise SolidWorksMCPError(
            f"Python 3.11+ required, but running {python_version.major}.{python_version.minor}"
        )

    logger.info("Environment validation complete")


async def _validate_solidworks_installation(config: SolidWorksMCPConfig) -> None:
    """Validate SolidWorks availability on Windows hosts.

    Args:
        config: Loaded server configuration.
    """
    try:
        # Check if SolidWorks executable exists
        if config.solidworks_path:
            if not shutil.which(config.solidworks_path):
                logger.warning(
                    f"SolidWorks executable not found at: {config.solidworks_path}"
                )

        # Try to check COM registration (basic check)
        try:
            import win32com.client

            # Try to create SolidWorks object (without starting it)
            win32com.client.Dispatch("SldWorks.Application", None)
            logger.info("SolidWorks COM interface is available")
        except Exception as e:
            logger.warning(f"SolidWorks COM interface issue: {e}")

    except ImportError:
        logger.warning("pywin32 not available for SolidWorks validation")
