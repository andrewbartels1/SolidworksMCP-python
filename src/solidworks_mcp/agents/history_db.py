"""SQLModel persistence for agent runs and tool-error cataloging."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select

DEFAULT_DB_PATH = Path(".solidworks_mcp") / "agent_memory.sqlite3"


class ErrorRecord(BaseModel):
    """A normalized error record from an MCP call or planning step."""

    source: str
    tool_name: str
    error_type: str
    error_message: str
    root_cause: str
    remediation: str


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AgentRun(SQLModel, table=True):
    """One recorded agent run."""

    id: int | None = Field(default=None, primary_key=True)
    run_id: str
    agent_name: str
    prompt: str
    model_name: str | None = None
    status: str
    output_json: str | None = None
    created_at: str


class ToolEvent(SQLModel, table=True):
    """One tool lifecycle event linked to a run."""

    id: int | None = Field(default=None, primary_key=True)
    run_id: str
    tool_name: str
    phase: str
    payload_json: str | None = None
    created_at: str


class ErrorCatalog(SQLModel, table=True):
    """Persisted error records for recovery recommendations."""

    id: int | None = Field(default=None, primary_key=True)
    run_id: str | None = None
    source: str
    tool_name: str
    error_type: str
    error_message: str
    root_cause: str
    remediation: str
    created_at: str


def _build_engine(db_path: Path | None = None):
    """Build a local SQLite engine from the configured path."""
    resolved = db_path or DEFAULT_DB_PATH
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{resolved}", echo=False)


def init_db(db_path: Path | None = None) -> Path:
    """Create SQLModel tables used by the lightweight agent memory system."""
    resolved = db_path or DEFAULT_DB_PATH
    engine = _build_engine(resolved)
    SQLModel.metadata.create_all(engine)
    return resolved


def insert_run(
    *,
    run_id: str,
    agent_name: str,
    prompt: str,
    status: str,
    output_json: str | None,
    model_name: str | None,
    db_path: Path | None = None,
) -> None:
    """Record one prompt run and optionally the validated output payload."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        session.add(
            AgentRun(
                run_id=run_id,
                agent_name=agent_name,
                prompt=prompt,
                model_name=model_name,
                status=status,
                output_json=output_json,
                created_at=_utc_now_iso(),
            )
        )
        session.commit()


def insert_tool_event(
    *,
    run_id: str,
    tool_name: str,
    phase: str,
    payload_json: str | None,
    db_path: Path | None = None,
) -> None:
    """Store lifecycle events around MCP tool usage to aid troubleshooting."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        session.add(
            ToolEvent(
                run_id=run_id,
                tool_name=tool_name,
                phase=phase,
                payload_json=payload_json,
                created_at=_utc_now_iso(),
            )
        )
        session.commit()


def insert_error(
    record: ErrorRecord, run_id: str | None = None, db_path: Path | None = None
) -> None:
    """Persist an error with normalized root cause and remediation guidance."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        session.add(
            ErrorCatalog(
                run_id=run_id,
                source=record.source,
                tool_name=record.tool_name,
                error_type=record.error_type,
                error_message=record.error_message,
                root_cause=record.root_cause,
                remediation=record.remediation,
                created_at=_utc_now_iso(),
            )
        )
        session.commit()


def find_recent_errors(
    limit: int = 20, db_path: Path | None = None
) -> list[dict[str, Any]]:
    """Return recent errors so agents can avoid repeated failing states."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        rows = session.exec(
            select(ErrorCatalog).order_by(ErrorCatalog.id.desc()).limit(limit)
        ).all()

    return [
        {
            "run_id": row.run_id,
            "source": row.source,
            "tool_name": row.tool_name,
            "error_type": row.error_type,
            "error_message": row.error_message,
            "root_cause": row.root_cause,
            "remediation": row.remediation,
            "created_at": row.created_at,
        }
        for row in rows
    ]
