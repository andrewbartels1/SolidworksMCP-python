"""Agent-testing utilities for SolidWorks MCP custom agents."""

from .harness import pretty_json, run_validated_prompt
from .history_db import (
    DEFAULT_DB_PATH,
    ErrorRecord,
    find_conversation_events,
    find_recent_errors,
    find_run_timeline,
    init_db,
    insert_conversation_event,
)
from .schemas import (
    DocsPlan,
    ManufacturabilityReview,
    RecoverableFailure,
    ToolRoutingDecision,
)
from .retrieval_index import build_local_retrieval_index

__all__ = [
    "DEFAULT_DB_PATH",
    "DocsPlan",
    "ErrorRecord",
    "ManufacturabilityReview",
    "RecoverableFailure",
    "ToolRoutingDecision",
    "build_local_retrieval_index",
    "find_conversation_events",
    "find_recent_errors",
    "find_run_timeline",
    "init_db",
    "insert_conversation_event",
    "pretty_json",
    "run_validated_prompt",
]
