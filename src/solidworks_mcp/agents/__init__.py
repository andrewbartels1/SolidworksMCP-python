"""Agent-testing utilities for SolidWorks MCP custom agents."""

from .harness import pretty_json, run_validated_prompt
from .history_db import DEFAULT_DB_PATH, ErrorRecord, find_recent_errors, init_db
from .schemas import (
    DocsPlan,
    ManufacturabilityReview,
    RecoverableFailure,
    ToolRoutingDecision,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "DocsPlan",
    "ErrorRecord",
    "ManufacturabilityReview",
    "RecoverableFailure",
    "ToolRoutingDecision",
    "find_recent_errors",
    "init_db",
    "pretty_json",
    "run_validated_prompt",
]
