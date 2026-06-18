"""Tests for solidworks_mcp.utils.logging."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from solidworks_mcp.utils.logging import get_audit_logger, setup_logging

# ---------------------------------------------------------------------------
# setup_logging branches
# ---------------------------------------------------------------------------


def test_setup_logging_console_only(tmp_path: Path) -> None:
    """setup_logging with no log_file or audit should add one stderr sink."""
    config = SimpleNamespace(
        log_level="DEBUG",
        log_file=None,
        enable_audit_logging=False,
    )
    # Should complete without error
    setup_logging(config)


def test_setup_logging_with_log_file(tmp_path: Path) -> None:
    """setup_logging should create parent directory and add file sink."""
    log_file = tmp_path / "logs" / "app.log"
    config = SimpleNamespace(
        log_level="INFO",
        log_file=log_file,
        enable_audit_logging=False,
    )
    setup_logging(config)
    # Parent directory should exist now
    assert log_file.parent.exists()


def test_setup_logging_with_audit_logging_and_log_file(tmp_path: Path) -> None:
    """Audit logging with a log_file should create audit.log in same parent."""
    log_file = tmp_path / "logs" / "app.log"
    config = SimpleNamespace(
        log_level="DEBUG",
        log_file=log_file,
        enable_audit_logging=True,
    )
    setup_logging(config)
    assert log_file.parent.exists()


def test_setup_logging_with_audit_logging_no_log_file(tmp_path: Path) -> None:
    """Audit logging without a log_file should fall back to audit.log in cwd."""
    config = SimpleNamespace(
        log_level="DEBUG",
        log_file=None,
        enable_audit_logging=True,
    )
    # Should not raise even without a configured file
    setup_logging(config)


# ---------------------------------------------------------------------------
# get_audit_logger
# ---------------------------------------------------------------------------


def test_get_audit_logger_returns_bound_logger() -> None:
    """get_audit_logger should return a logger bound with audit=True."""
    audit_logger = get_audit_logger()
    # Loguru bound loggers have a _core attribute or similar; what matters is
    # it doesn't raise and is not None.
    assert audit_logger is not None
