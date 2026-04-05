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


class ConversationEvent(SQLModel, table=True):
    """One message or system event in a conversation, linked to a run context."""

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str
    run_id: str | None = None
    event_type: str  # "user_message", "assistant_message", "system_event", "tool_call"
    role: str | None = None  # "user", "assistant", "system"
    content_snippet: str  # truncated for privacy; full content may be elsewhere
    metadata_json: str | None = None  # tool_name, phase, status, etc.
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


def insert_conversation_event(
    *,
    conversation_id: str,
    event_type: str,
    content_snippet: str,
    role: str | None = None,
    run_id: str | None = None,
    metadata_json: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Record a conversation event (message, system event, or tool call) linked to a run."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        session.add(
            ConversationEvent(
                conversation_id=conversation_id,
                run_id=run_id,
                event_type=event_type,
                role=role,
                content_snippet=content_snippet,
                metadata_json=metadata_json,
                created_at=_utc_now_iso(),
            )
        )
        session.commit()


def find_conversation_events(
    conversation_id: str, db_path: Path | None = None
) -> list[dict[str, Any]]:
    """Retrieve all events for a conversation, ordered by creation time."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        rows = session.exec(
            select(ConversationEvent)
            .where(ConversationEvent.conversation_id == conversation_id)
            .order_by(ConversationEvent.id.asc())
        ).all()

    return [
        {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "run_id": row.run_id,
            "event_type": row.event_type,
            "role": row.role,
            "content_snippet": row.content_snippet,
            "metadata_json": row.metadata_json,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def find_run_timeline(run_id: str, db_path: Path | None = None) -> dict[str, Any]:
    """Reconstruct a complete timeline for one run, joining runs, tool events, and conversation events."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)

    timeline: dict[str, Any] = {
        "run_id": run_id,
        "run_info": None,
        "events": [],
    }

    with Session(engine) as session:
        run_row = session.exec(
            select(AgentRun).where(AgentRun.run_id == run_id)
        ).first()

        if run_row:
            timeline["run_info"] = {
                "agent_name": run_row.agent_name,
                "prompt_preview": run_row.prompt[:200] if run_row.prompt else None,
                "model_name": run_row.model_name,
                "status": run_row.status,
                "created_at": run_row.created_at,
            }

        tool_events = session.exec(
            select(ToolEvent)
            .where(ToolEvent.run_id == run_id)
            .order_by(ToolEvent.id.asc())
        ).all()

        convo_events = session.exec(
            select(ConversationEvent)
            .where(ConversationEvent.run_id == run_id)
            .order_by(ConversationEvent.id.asc())
        ).all()

        events = []
        for evt in tool_events:
            events.append(
                {
                    "timestamp": evt.created_at,
                    "event_type": "tool",
                    "tool_name": evt.tool_name,
                    "phase": evt.phase,
                    "payload_preview": evt.payload_json[:100]
                    if evt.payload_json
                    else None,
                }
            )

        for evt in convo_events:
            events.append(
                {
                    "timestamp": evt.created_at,
                    "event_type": "message",
                    "role": evt.role,
                    "content_preview": evt.content_snippet[:100],
                    "metadata": evt.metadata_json,
                }
            )

        events.sort(key=lambda e: e["timestamp"])
        timeline["events"] = events

    return timeline
