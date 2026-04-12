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


class DesignSession(SQLModel, table=True):
    """Persistent interactive design session metadata."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    user_goal: str
    source_mode: str = "model"  # model/image/text
    accepted_family: str | None = None
    status: str = "active"
    current_checkpoint_index: int = 0
    metadata_json: str | None = None
    created_at: str
    updated_at: str


class PlanCheckpoint(SQLModel, table=True):
    """One approval boundary in an interactive design session."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    checkpoint_index: int
    title: str
    planned_action_json: str
    approved_by_user: bool = False
    executed: bool = False
    result_json: str | None = None
    rollback_snapshot_id: int | None = None
    created_at: str
    updated_at: str


class ToolCallRecord(SQLModel, table=True):
    """Execution log for tool calls scoped to session/checkpoint."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    checkpoint_id: int | None = None
    run_id: str | None = None
    tool_name: str
    input_json: str | None = None
    output_json: str | None = None
    success: bool = True
    latency_ms: float | None = None
    created_at: str


class EvidenceLink(SQLModel, table=True):
    """Evidence references used to justify planning decisions."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    checkpoint_id: int | None = None
    source_type: str
    source_id: str
    relevance_score: float | None = None
    rationale: str | None = None
    payload_json: str | None = None
    created_at: str


class ModelStateSnapshot(SQLModel, table=True):
    """Rollback/diff snapshot of model state at a checkpoint."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    checkpoint_id: int | None = None
    model_path: str | None = None
    feature_tree_json: str | None = None
    mass_properties_json: str | None = None
    screenshot_path: str | None = None
    state_fingerprint: str | None = None
    created_at: str


class SketchGraphSnapshot(SQLModel, table=True):
    """Lightweight relational sketch graph storage (Section F)."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    model_path: str | None = None
    graph_format: str = "json"
    nodes_json: str
    edges_json: str
    metadata_json: str | None = None
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


def upsert_design_session(
    *,
    session_id: str,
    user_goal: str,
    source_mode: str = "model",
    accepted_family: str | None = None,
    status: str = "active",
    current_checkpoint_index: int = 0,
    metadata_json: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Create or update one interactive design session row."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    now = _utc_now_iso()
    with Session(engine) as session:
        row = session.exec(
            select(DesignSession).where(DesignSession.session_id == session_id)
        ).first()
        if row is None:
            session.add(
                DesignSession(
                    session_id=session_id,
                    user_goal=user_goal,
                    source_mode=source_mode,
                    accepted_family=accepted_family,
                    status=status,
                    current_checkpoint_index=current_checkpoint_index,
                    metadata_json=metadata_json,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            row.user_goal = user_goal
            row.source_mode = source_mode
            row.accepted_family = accepted_family
            row.status = status
            row.current_checkpoint_index = current_checkpoint_index
            row.metadata_json = metadata_json
            row.updated_at = now
            session.add(row)
        session.commit()


def get_design_session(
    session_id: str, db_path: Path | None = None
) -> dict[str, Any] | None:
    """Return one session row as a dictionary."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        row = session.exec(
            select(DesignSession).where(DesignSession.session_id == session_id)
        ).first()

    if row is None:
        return None
    return {
        "session_id": row.session_id,
        "user_goal": row.user_goal,
        "source_mode": row.source_mode,
        "accepted_family": row.accepted_family,
        "status": row.status,
        "current_checkpoint_index": row.current_checkpoint_index,
        "metadata_json": row.metadata_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def insert_plan_checkpoint(
    *,
    session_id: str,
    checkpoint_index: int,
    title: str,
    planned_action_json: str,
    approved_by_user: bool = False,
    executed: bool = False,
    result_json: str | None = None,
    rollback_snapshot_id: int | None = None,
    db_path: Path | None = None,
) -> int:
    """Insert a new checkpoint and return its ID."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    now = _utc_now_iso()
    with Session(engine) as session:
        row = PlanCheckpoint(
            session_id=session_id,
            checkpoint_index=checkpoint_index,
            title=title,
            planned_action_json=planned_action_json,
            approved_by_user=approved_by_user,
            executed=executed,
            result_json=result_json,
            rollback_snapshot_id=rollback_snapshot_id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id or 0)


def update_plan_checkpoint(
    checkpoint_id: int,
    *,
    approved_by_user: bool | None = None,
    executed: bool | None = None,
    result_json: str | None = None,
    rollback_snapshot_id: int | None = None,
    db_path: Path | None = None,
) -> None:
    """Patch checkpoint approval/execution fields."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        row = session.exec(
            select(PlanCheckpoint).where(PlanCheckpoint.id == checkpoint_id)
        ).first()
        if row is None:
            return
        if approved_by_user is not None:
            row.approved_by_user = approved_by_user
        if executed is not None:
            row.executed = executed
        if result_json is not None:
            row.result_json = result_json
        if rollback_snapshot_id is not None:
            row.rollback_snapshot_id = rollback_snapshot_id
        row.updated_at = _utc_now_iso()
        session.add(row)
        session.commit()


def list_plan_checkpoints(
    session_id: str,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List all checkpoints for a session."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        rows = session.exec(
            select(PlanCheckpoint)
            .where(PlanCheckpoint.session_id == session_id)
            .order_by(PlanCheckpoint.checkpoint_index.asc())
        ).all()

    return [
        {
            "id": row.id,
            "session_id": row.session_id,
            "checkpoint_index": row.checkpoint_index,
            "title": row.title,
            "planned_action_json": row.planned_action_json,
            "approved_by_user": row.approved_by_user,
            "executed": row.executed,
            "result_json": row.result_json,
            "rollback_snapshot_id": row.rollback_snapshot_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def insert_tool_call_record(
    *,
    session_id: str,
    tool_name: str,
    checkpoint_id: int | None = None,
    run_id: str | None = None,
    input_json: str | None = None,
    output_json: str | None = None,
    success: bool = True,
    latency_ms: float | None = None,
    db_path: Path | None = None,
) -> None:
    """Insert one tool call execution record."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        session.add(
            ToolCallRecord(
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                tool_name=tool_name,
                input_json=input_json,
                output_json=output_json,
                success=success,
                latency_ms=latency_ms,
                created_at=_utc_now_iso(),
            )
        )
        session.commit()


def list_tool_call_records(
    session_id: str,
    checkpoint_id: int | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List tool call records for a session and optional checkpoint."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        query = select(ToolCallRecord).where(ToolCallRecord.session_id == session_id)
        if checkpoint_id is not None:
            query = query.where(ToolCallRecord.checkpoint_id == checkpoint_id)
        rows = session.exec(query.order_by(ToolCallRecord.id.asc())).all()

    return [
        {
            "id": row.id,
            "session_id": row.session_id,
            "checkpoint_id": row.checkpoint_id,
            "run_id": row.run_id,
            "tool_name": row.tool_name,
            "input_json": row.input_json,
            "output_json": row.output_json,
            "success": row.success,
            "latency_ms": row.latency_ms,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def insert_evidence_link(
    *,
    session_id: str,
    source_type: str,
    source_id: str,
    checkpoint_id: int | None = None,
    relevance_score: float | None = None,
    rationale: str | None = None,
    payload_json: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Insert one evidence row used by planning/classification."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        session.add(
            EvidenceLink(
                session_id=session_id,
                checkpoint_id=checkpoint_id,
                source_type=source_type,
                source_id=source_id,
                relevance_score=relevance_score,
                rationale=rationale,
                payload_json=payload_json,
                created_at=_utc_now_iso(),
            )
        )
        session.commit()


def list_evidence_links(
    session_id: str,
    checkpoint_id: int | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List evidence rows for a session and optional checkpoint."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        query = select(EvidenceLink).where(EvidenceLink.session_id == session_id)
        if checkpoint_id is not None:
            query = query.where(EvidenceLink.checkpoint_id == checkpoint_id)
        rows = session.exec(query.order_by(EvidenceLink.id.asc())).all()

    return [
        {
            "id": row.id,
            "session_id": row.session_id,
            "checkpoint_id": row.checkpoint_id,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "relevance_score": row.relevance_score,
            "rationale": row.rationale,
            "payload_json": row.payload_json,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def insert_model_state_snapshot(
    *,
    session_id: str,
    checkpoint_id: int | None = None,
    model_path: str | None = None,
    feature_tree_json: str | None = None,
    mass_properties_json: str | None = None,
    screenshot_path: str | None = None,
    state_fingerprint: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Insert model snapshot row and return snapshot ID for rollback tracking."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        row = ModelStateSnapshot(
            session_id=session_id,
            checkpoint_id=checkpoint_id,
            model_path=model_path,
            feature_tree_json=feature_tree_json,
            mass_properties_json=mass_properties_json,
            screenshot_path=screenshot_path,
            state_fingerprint=state_fingerprint,
            created_at=_utc_now_iso(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id or 0)


def list_model_state_snapshots(
    session_id: str,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List snapshots for a session newest first for diff/rollback flows."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        rows = session.exec(
            select(ModelStateSnapshot)
            .where(ModelStateSnapshot.session_id == session_id)
            .order_by(ModelStateSnapshot.id.desc())
        ).all()

    return [
        {
            "id": row.id,
            "session_id": row.session_id,
            "checkpoint_id": row.checkpoint_id,
            "model_path": row.model_path,
            "feature_tree_json": row.feature_tree_json,
            "mass_properties_json": row.mass_properties_json,
            "screenshot_path": row.screenshot_path,
            "state_fingerprint": row.state_fingerprint,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def insert_sketch_graph_snapshot(
    *,
    session_id: str,
    nodes_json: str,
    edges_json: str,
    model_path: str | None = None,
    graph_format: str = "json",
    metadata_json: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Store lightweight sketch graph snapshots in SQLite (Section F)."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        session.add(
            SketchGraphSnapshot(
                session_id=session_id,
                model_path=model_path,
                graph_format=graph_format,
                nodes_json=nodes_json,
                edges_json=edges_json,
                metadata_json=metadata_json,
                created_at=_utc_now_iso(),
            )
        )
        session.commit()


def list_sketch_graph_snapshots(
    session_id: str,
    model_path: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List sketch graph snapshots for a session."""
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        query = select(SketchGraphSnapshot).where(
            SketchGraphSnapshot.session_id == session_id
        )
        if model_path is not None:
            query = query.where(SketchGraphSnapshot.model_path == model_path)
        rows = session.exec(query.order_by(SketchGraphSnapshot.id.desc())).all()

    return [
        {
            "id": row.id,
            "session_id": row.session_id,
            "model_path": row.model_path,
            "graph_format": row.graph_format,
            "nodes_json": row.nodes_json,
            "edges_json": row.edges_json,
            "metadata_json": row.metadata_json,
            "created_at": row.created_at,
        }
        for row in rows
    ]
