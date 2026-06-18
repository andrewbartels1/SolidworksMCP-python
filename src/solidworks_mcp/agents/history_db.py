"""SQLModel persistence for agent runs and tool-error cataloging."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy.pool import NullPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

DEFAULT_DB_PATH = Path(".solidworks_mcp") / "agent_memory.sqlite3"


class ErrorRecord(BaseModel):
    """A normalized error record from an MCP call or planning step.

    Attributes:
        error_message (str): The error message value.
        error_type (str): The error type value.
        remediation (str): The remediation value.
        root_cause (str): The root cause value.
        source (str): The source value.
        tool_name (str): The tool name value.
    """

    source: str
    tool_name: str
    error_type: str
    error_message: str
    root_cause: str
    remediation: str


def _utc_now_iso() -> str:
    """Build internal utc now iso.

    Returns:
        str: The resulting text value.
    """

    return datetime.now(UTC).isoformat()


class AgentRun(SQLModel, table=True):
    """One recorded agent run.

    Attributes:
        agent_name (str): The agent name value.
        created_at (str): The created at value.
        id (int | None): The id value.
        model_name (str | None): The model name value.
        output_json (str | None): The output json value.
        prompt (str): The prompt value.
        run_id (str): The run id value.
        status (str): The status value.
    """

    id: int | None = Field(default=None, primary_key=True)
    run_id: str
    agent_name: str
    prompt: str
    model_name: str | None = None
    status: str
    output_json: str | None = None
    created_at: str


class ToolEvent(SQLModel, table=True):
    """One tool lifecycle event linked to a run.

    Attributes:
        created_at (str): The created at value.
        id (int | None): The id value.
        payload_json (str | None): The payload json value.
        phase (str): The phase value.
        run_id (str): The run id value.
        tool_name (str): The tool name value.
    """

    id: int | None = Field(default=None, primary_key=True)
    run_id: str
    tool_name: str
    phase: str
    payload_json: str | None = None
    created_at: str


class ErrorCatalog(SQLModel, table=True):
    """Persisted error records for recovery recommendations.

    Attributes:
        created_at (str): The created at value.
        error_message (str): The error message value.
        error_type (str): The error type value.
        id (int | None): The id value.
        remediation (str): The remediation value.
        root_cause (str): The root cause value.
        run_id (str | None): The run id value.
        source (str): The source value.
        tool_name (str): The tool name value.
    """

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
    """One message or system event in a conversation, linked to a run context.

    Attributes:
        content_snippet (str): The content snippet value.
        conversation_id (str): The conversation id value.
        created_at (str): The created at value.
        event_type (str): The event type value.
        id (int | None): The id value.
        metadata_json (str | None): The metadata json value.
        role (str | None): The role value.
        run_id (str | None): The run id value.
    """

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str
    run_id: str | None = None
    event_type: str  # "user_message", "assistant_message", "system_event", "tool_call"
    role: str | None = None  # "user", "assistant", "system"
    content_snippet: str  # truncated for privacy; full content may be elsewhere
    metadata_json: str | None = None  # tool_name, phase, status, etc.
    created_at: str


class DesignSession(SQLModel, table=True):
    """Persistent interactive design session metadata.

    Attributes:
        accepted_family (str | None): The accepted family value.
        created_at (str): The created at value.
        current_checkpoint_index (int): The current checkpoint index value.
        id (int | None): The id value.
        metadata_json (str | None): The metadata json value.
        session_id (str): The session id value.
        source_mode (str): The source mode value.
        status (str): The status value.
        updated_at (str): The updated at value.
        user_goal (str): The user goal value.
    """

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
    """One approval boundary in an interactive design session.

    Attributes:
        approved_by_user (bool): The approved by user value.
        checkpoint_index (int): The checkpoint index value.
        created_at (str): The created at value.
        executed (bool): The executed value.
        id (int | None): The id value.
        planned_action_json (str): The planned action json value.
        result_json (str | None): The result json value.
        rollback_snapshot_id (int | None): The rollback snapshot id value.
        session_id (str): The session id value.
        title (str): The title value.
        updated_at (str): The updated at value.
    """

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
    """Execution log for tool calls scoped to session/checkpoint.

    Attributes:
        checkpoint_id (int | None): The checkpoint id value.
        created_at (str): The created at value.
        id (int | None): The id value.
        input_json (str | None): The input json value.
        latency_ms (float | None): The latency ms value.
        output_json (str | None): The output json value.
        run_id (str | None): The run id value.
        session_id (str): The session id value.
        status (str | None): Lifecycle status — None (active), 'reverted'.
        success (bool): The success value.
        tool_name (str): The tool name value.
    """

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    checkpoint_id: int | None = None
    run_id: str | None = None
    tool_name: str
    input_json: str | None = None
    output_json: str | None = None
    success: bool = True
    latency_ms: float | None = None
    status: str | None = None
    created_at: str


class EvidenceLink(SQLModel, table=True):
    """Evidence references used to justify planning decisions.

    Attributes:
        checkpoint_id (int | None): The checkpoint id value.
        created_at (str): The created at value.
        id (int | None): The id value.
        payload_json (str | None): The payload json value.
        rationale (str | None): The rationale value.
        relevance_score (float | None): The relevance score value.
        session_id (str): The session id value.
        source_id (str): The source id value.
        source_type (str): The source type value.
    """

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
    """Rollback/diff snapshot of model state at a checkpoint.

    Attributes:
        checkpoint_id (int | None): The checkpoint id value.
        created_at (str): The created at value.
        feature_tree_json (str | None): The feature tree json value.
        id (int | None): The id value.
        mass_properties_json (str | None): The mass properties json value.
        model_path (str | None): The model path value.
        screenshot_path (str | None): The screenshot path value.
        session_id (str): The session id value.
        state_fingerprint (str | None): The state fingerprint value.
    """

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    checkpoint_id: int | None = None
    model_path: str | None = None
    feature_tree_json: str | None = None
    mass_properties_json: str | None = None
    screenshot_path: str | None = None
    state_fingerprint: str | None = None
    created_at: str


class SoCCheckpoint(SQLModel, table=True):
    """Named save point in a SolidWorks-as-Code session.

    A checkpoint ties together a human label, the saved .sldprt file that
    represents the model state at that point, and the range of ToolCallRecord
    rows that produced it.  The exporter uses this to emit structured comment
    blocks; soc_rewind uses the file_path to restore the model; soc_pickup
    uses snapshot_id to diff against the current feature tree.

    Attributes:
        file_path (str): Path to the .sldprt saved at this checkpoint.
        first_record_id (int | None): First ToolCallRecord.id in this block.
        id (int | None): Primary key.
        label (str): Short human name for this checkpoint.
        last_record_id (int | None): Last ToolCallRecord.id in this block.
        session_id (str): Owning SoC session.
        snapshot_id (int | None): FK to ModelStateSnapshot (feature tree, mass props).
        created_at (str): ISO timestamp.
    """

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    label: str
    file_path: str
    first_record_id: int | None = None
    last_record_id: int | None = None
    snapshot_id: int | None = None
    created_at: str


class SketchGraphSnapshot(SQLModel, table=True):
    """Lightweight relational sketch graph storage (Section F).

    Attributes:
        created_at (str): The created at value.
        edges_json (str): The edges json value.
        graph_format (str): The graph format value.
        id (int | None): The id value.
        metadata_json (str | None): The metadata json value.
        model_path (str | None): The model path value.
        nodes_json (str): The nodes json value.
        session_id (str): The session id value.
    """

    id: int | None = Field(default=None, primary_key=True)
    session_id: str
    model_path: str | None = None
    graph_format: str = "json"
    nodes_json: str
    edges_json: str
    metadata_json: str | None = None
    created_at: str


def _build_engine(db_path: Path | None = None) -> Any:
    """Build a local SQLite engine from the configured path.

    Args:
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        Any: SQLAlchemy engine instance for the resolved SQLite path.
    """
    resolved = db_path or DEFAULT_DB_PATH
    resolved.parent.mkdir(parents=True, exist_ok=True)
    # NullPool closes sqlite connections immediately after each session/transaction,
    # which prevents a long-lived pool from surfacing ResourceWarning noise at process exit.
    return create_engine(f"sqlite:///{resolved}", echo=False, poolclass=NullPool)


def init_db(db_path: Path | None = None) -> Path:
    """Create SQLModel tables used by the lightweight agent memory system.

    Args:
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        Path: The result produced by the operation.
    """
    resolved = db_path or DEFAULT_DB_PATH
    engine = _build_engine(resolved)
    try:
        SQLModel.metadata.create_all(engine)
    finally:
        engine.dispose()
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
    """Record one prompt run and optionally the validated output payload.

    Args:
        run_id (str): The run id value.
        agent_name (str): The agent name value.
        prompt (str): The prompt value.
        status (str): The status value.
        output_json (str | None): The output json value.
        model_name (str | None): Embedding model name to use.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
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
    """Store lifecycle events around MCP tool usage to aid troubleshooting.

    Args:
        run_id (str): The run id value.
        tool_name (str): The tool name value.
        phase (str): The phase value.
        payload_json (str | None): The payload json value.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
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
    """Persist an error with normalized root cause and remediation guidance.

    Args:
        record (ErrorRecord): The record value.
        run_id (str | None): The run id value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
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
    """Return recent errors so agents can avoid repeated failing states.

    Args:
        limit (int): The limit value. Defaults to 20.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        rows = session.exec(
            select(ErrorCatalog).order_by(ErrorCatalog.id.desc()).limit(limit)  # type: ignore[union-attr]
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
    """Record a conversation event (message, system event, or tool call) linked to a run.

    Args:
        conversation_id (str): The conversation id value.
        event_type (str): The event type value.
        content_snippet (str): The content snippet value.
        role (str | None): The role value. Defaults to None.
        run_id (str | None): The run id value. Defaults to None.
        metadata_json (str | None): The metadata json value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
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
    """Retrieve all events for a conversation, ordered by creation time.

    Args:
        conversation_id (str): The conversation id value.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        rows = session.exec(
            select(ConversationEvent)
            .where(ConversationEvent.conversation_id == conversation_id)
            .order_by(ConversationEvent.id.asc())  # type: ignore[union-attr]
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
    """Reconstruct a complete timeline for one run, joining runs, tool events, and conversation events.

    Args:
        run_id (str): The run id value.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
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
            .order_by(ToolEvent.id.asc())  # type: ignore[union-attr]
        ).all()

        convo_events = session.exec(
            select(ConversationEvent)
            .where(ConversationEvent.run_id == run_id)
            .order_by(ConversationEvent.id.asc())  # type: ignore[union-attr]
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

        for conv_evt in convo_events:
            events.append(
                {
                    "timestamp": conv_evt.created_at,
                    "event_type": "message",
                    "role": conv_evt.role,
                    "content_preview": conv_evt.content_snippet[:100],
                    "metadata": conv_evt.metadata_json,
                }
            )

        events.sort(key=lambda e: e["timestamp"] or "")
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
    """Create or update one interactive design session row.

    Args:
        session_id (str): The session id value.
        user_goal (str): The user goal value.
        source_mode (str): The source mode value. Defaults to "model".
        accepted_family (str | None): The accepted family value. Defaults to None.
        status (str): The status value. Defaults to "active".
        current_checkpoint_index (int): The current checkpoint index value. Defaults to 0.
        metadata_json (str | None): The metadata json value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
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
    """Return one session row as a dictionary.

    Args:
        session_id (str): The session id value.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        dict[str, Any] | None: A dictionary containing the resulting values.
    """
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
    """Insert a new checkpoint and return its ID.

    Args:
        session_id (str): The session id value.
        checkpoint_index (int): The checkpoint index value.
        title (str): The title value.
        planned_action_json (str): The planned action json value.
        approved_by_user (bool): The approved by user value. Defaults to False.
        executed (bool): The executed value. Defaults to False.
        result_json (str | None): The result json value. Defaults to None.
        rollback_snapshot_id (int | None): The rollback snapshot id value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        int: The computed numeric result.
    """
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
    """Patch checkpoint approval/execution fields.

    Args:
        checkpoint_id (int): The checkpoint id value.
        approved_by_user (bool | None): The approved by user value. Defaults to None.
        executed (bool | None): The executed value. Defaults to None.
        result_json (str | None): The result json value. Defaults to None.
        rollback_snapshot_id (int | None): The rollback snapshot id value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
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


def update_plan_checkpoint_planned_action(
    checkpoint_id: int,
    *,
    planned_action_json: str,
    executed: bool | None = None,
    result_json: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Update checkpoint planned-action JSON and optional execution status.

    Args:
        checkpoint_id: Target checkpoint row ID.
        planned_action_json: New planned action payload encoded as JSON string.
        executed: Optional executed flag override.
        result_json: Optional result payload override.
        db_path: Optional SQLite path override.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        row = session.exec(
            select(PlanCheckpoint).where(PlanCheckpoint.id == checkpoint_id)
        ).first()
        if row is None:
            return

        row.planned_action_json = planned_action_json
        if executed is not None:
            row.executed = executed
        if result_json is not None:
            row.result_json = result_json
        row.updated_at = _utc_now_iso()

        session.add(row)
        session.commit()


def list_plan_checkpoints(
    session_id: str,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List all checkpoints for a session.

    Args:
        session_id (str): The session id value.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        rows = session.exec(
            select(PlanCheckpoint)
            .where(PlanCheckpoint.session_id == session_id)
            .order_by(PlanCheckpoint.checkpoint_index.asc())  # type: ignore[attr-defined]
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


def replace_plan_checkpoints(
    *,
    session_id: str,
    checkpoints: list[dict[str, Any]],
    db_path: Path | None = None,
) -> None:
    """Replace all session checkpoints with a new ordered checkpoint list.

    Args:
        session_id (str): The session id value.
        checkpoints (list[dict[str, Any]]): Replacement checkpoint records.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    now = _utc_now_iso()

    with Session(engine) as session:
        existing_rows = session.exec(
            select(PlanCheckpoint).where(PlanCheckpoint.session_id == session_id)
        ).all()
        for existing in existing_rows:
            session.delete(existing)

        for index, item in enumerate(checkpoints, start=1):
            planned_action_json = str(item.get("planned_action_json") or "{}")
            title = str(item.get("title") or f"Checkpoint {index}")
            approved_by_user = bool(item.get("approved_by_user", index == 1))
            row = PlanCheckpoint(
                session_id=session_id,
                checkpoint_index=int(item.get("checkpoint_index") or index),
                title=title,
                planned_action_json=planned_action_json,
                approved_by_user=approved_by_user,
                executed=False,
                result_json=None,
                rollback_snapshot_id=None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)

        session.commit()


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
    """Insert one tool call execution record.

    Args:
        session_id (str): The session id value.
        tool_name (str): The tool name value.
        checkpoint_id (int | None): The checkpoint id value. Defaults to None.
        run_id (str | None): The run id value. Defaults to None.
        input_json (str | None): The input json value. Defaults to None.
        output_json (str | None): The output json value. Defaults to None.
        success (bool): The success value. Defaults to True.
        latency_ms (float | None): The latency ms value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
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
    include_reverted: bool = False,
) -> list[dict[str, Any]]:
    """List tool call records for a session and optional checkpoint.

    Args:
        session_id (str): The session id value.
        checkpoint_id (int | None): The checkpoint id value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.
        include_reverted (bool): Include records with status='reverted'. Defaults to False.

    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        query = select(ToolCallRecord).where(ToolCallRecord.session_id == session_id)
        if checkpoint_id is not None:
            query = query.where(ToolCallRecord.checkpoint_id == checkpoint_id)
        if not include_reverted:
            query = query.where(
                (ToolCallRecord.status == None) | (ToolCallRecord.status != "reverted")  # noqa: E711
            )
        rows = session.exec(query.order_by(ToolCallRecord.id.asc())).all()  # type: ignore[union-attr]

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
            "status": row.status,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def revert_tool_call_records(
    session_id: str,
    from_record_id: int,
    db_path: Path | None = None,
) -> int:
    """Mark ToolCallRecords as reverted from from_record_id onward.

    Sets status='reverted' on all records for the session with id >= from_record_id.
    Reverted records are excluded from list_tool_call_records() by default and from
    the soc_exporter output, so re-generating the script omits the rolled-back work.

    Args:
        session_id (str): The SoC session whose records should be reverted.
        from_record_id (int): First record ID to mark as reverted (inclusive).
        db_path (Path | None): Override default SQLite DB path.

    Returns:
        int: Number of records marked reverted.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as db_session:
        rows = db_session.exec(
            select(ToolCallRecord)
            .where(ToolCallRecord.session_id == session_id)
            .where(ToolCallRecord.id >= from_record_id)  # type: ignore[operator]
        ).all()
        for row in rows:
            row.status = "reverted"
        db_session.commit()
    return len(rows)


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
    """Insert one evidence row used by planning/classification.

    Args:
        session_id (str): The session id value.
        source_type (str): The source type value.
        source_id (str): The source id value.
        checkpoint_id (int | None): The checkpoint id value. Defaults to None.
        relevance_score (float | None): The relevance score value. Defaults to None.
        rationale (str | None): The rationale value. Defaults to None.
        payload_json (str | None): The payload json value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
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
    """List evidence rows for a session and optional checkpoint.

    Args:
        session_id (str): The session id value.
        checkpoint_id (int | None): The checkpoint id value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        query = select(EvidenceLink).where(EvidenceLink.session_id == session_id)
        if checkpoint_id is not None:
            query = query.where(EvidenceLink.checkpoint_id == checkpoint_id)
        rows = session.exec(query.order_by(EvidenceLink.id.asc())).all()  # type: ignore[union-attr]

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
    """Insert model snapshot row and return snapshot ID for rollback tracking.

    Args:
        session_id (str): The session id value.
        checkpoint_id (int | None): The checkpoint id value. Defaults to None.
        model_path (str | None): The model path value. Defaults to None.
        feature_tree_json (str | None): The feature tree json value. Defaults to None.
        mass_properties_json (str | None): The mass properties json value. Defaults to None.
        screenshot_path (str | None): The screenshot path value. Defaults to None.
        state_fingerprint (str | None): The state fingerprint value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        int: The computed numeric result.
    """
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
    """List snapshots for a session newest first for diff/rollback flows.

    Args:
        session_id (str): The session id value.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        rows = session.exec(
            select(ModelStateSnapshot)
            .where(ModelStateSnapshot.session_id == session_id)
            .order_by(ModelStateSnapshot.id.desc())  # type: ignore[union-attr]
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


def create_soc_checkpoint(
    *,
    session_id: str,
    label: str,
    file_path: str,
    first_record_id: int | None = None,
    last_record_id: int | None = None,
    snapshot_id: int | None = None,
    db_path: Path | None = None,
) -> int:
    """Insert a SoCCheckpoint and return its id.

    Args:
        session_id (str): Owning SoC session.
        label (str): Short human name (e.g. "base-extrude").
        file_path (str): Path to the .sldprt saved at this checkpoint.
        first_record_id (int | None): First ToolCallRecord.id in this block.
        last_record_id (int | None): Last ToolCallRecord.id in this block.
        snapshot_id (int | None): FK to ModelStateSnapshot.
        db_path (Path | None): Override default SQLite path.

    Returns:
        int: The new SoCCheckpoint.id.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        row = SoCCheckpoint(
            session_id=session_id,
            label=label,
            file_path=file_path,
            first_record_id=first_record_id,
            last_record_id=last_record_id,
            snapshot_id=snapshot_id,
            created_at=_utc_now_iso(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id)  # type: ignore[arg-type]


def list_soc_checkpoints(
    session_id: str,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """List SoCCheckpoints for a session in creation order.

    Args:
        session_id (str): Owning SoC session.
        db_path (Path | None): Override default SQLite path.

    Returns:
        list[dict[str, Any]]: Ordered list of checkpoint dicts.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        rows = session.exec(
            select(SoCCheckpoint)
            .where(SoCCheckpoint.session_id == session_id)
            .order_by(SoCCheckpoint.id.asc())  # type: ignore[union-attr]
        ).all()
    return [
        {
            "id": row.id,
            "session_id": row.session_id,
            "label": row.label,
            "file_path": row.file_path,
            "first_record_id": row.first_record_id,
            "last_record_id": row.last_record_id,
            "snapshot_id": row.snapshot_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def get_soc_checkpoint(
    session_id: str,
    label: str,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Fetch a single SoCCheckpoint by session + label.

    Args:
        session_id (str): Owning SoC session.
        label (str): Checkpoint label to look up.
        db_path (Path | None): Override default SQLite path.

    Returns:
        dict[str, Any] | None: Checkpoint dict or None if not found.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        row = session.exec(
            select(SoCCheckpoint)
            .where(SoCCheckpoint.session_id == session_id)
            .where(SoCCheckpoint.label == label)
            .order_by(SoCCheckpoint.id.desc())  # type: ignore[union-attr]
        ).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "session_id": row.session_id,
        "label": row.label,
        "file_path": row.file_path,
        "first_record_id": row.first_record_id,
        "last_record_id": row.last_record_id,
        "snapshot_id": row.snapshot_id,
        "created_at": row.created_at,
    }


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
    """Store lightweight sketch graph snapshots in SQLite (Section F).

    Args:
        session_id (str): The session id value.
        nodes_json (str): The nodes json value.
        edges_json (str): The edges json value.
        model_path (str | None): The model path value. Defaults to None.
        graph_format (str): The graph format value. Defaults to "json".
        metadata_json (str | None): The metadata json value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        None: None.
    """
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
    """List sketch graph snapshots for a session.

    Args:
        session_id (str): The session id value.
        model_path (str | None): The model path value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.

    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """
    resolved = init_db(db_path)
    engine = _build_engine(resolved)
    with Session(engine) as session:
        query = select(SketchGraphSnapshot).where(
            SketchGraphSnapshot.session_id == session_id
        )
        if model_path is not None:
            query = query.where(SketchGraphSnapshot.model_path == model_path)
        rows = session.exec(query.order_by(SketchGraphSnapshot.id.desc())).all()  # type: ignore[union-attr]

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
