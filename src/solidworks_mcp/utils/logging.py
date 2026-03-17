"""
Logging configuration for SolidWorks MCP Server.
"""

import sys
from pathlib import Path
from loguru import logger


def setup_logging(config) -> None:
    """Setup logging configuration based on config."""
    # Remove default handler
    logger.remove()

    # Console logging
    logger.add(
        sys.stderr,
        level=config.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>",
        colorize=True,
    )

    # File logging
    if config.log_file:
        # Ensure log directory exists
        config.log_file.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            config.log_file,
            level=config.log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            rotation="10 MB",
            retention="1 week",
        )

    # Audit logging for security
    if config.enable_audit_logging:
        audit_log = (
            config.log_file.parent / "audit.log"
            if config.log_file
            else Path("audit.log")
        )
        audit_log.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            audit_log,
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | AUDIT | {extra[audit_type]} | {message}",
            filter=lambda record: "audit" in record["extra"],
            rotation="1 day",
            retention="30 days",
            compression="gzip",
        )

    logger.info("Logging configured")


def get_audit_logger():
    """Get logger for audit events."""
    return logger.bind(audit=True)
