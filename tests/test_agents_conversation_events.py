"""Tests for conversation event logging in history_db.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.solidworks_mcp.agents.history_db import (
    ConversationEvent,
    find_conversation_events,
    find_run_timeline,
    init_db,
    insert_conversation_event,
    insert_run,
    insert_tool_event,
)


def _db(tmp_path: Path) -> Path:
    """Return a test-specific DB path."""
    return tmp_path / "test_agent_memory.sqlite3"


def _query_all(db: Path, model_class: type) -> list:
    """Query all rows from a table."""
    from sqlmodel import Session, create_engine, select

    engine = create_engine(f"sqlite:///{db}")
    with Session(engine) as session:
        return session.exec(select(model_class)).all()


class TestInsertConversationEvent:
    def test_inserts_user_message(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_conversation_event(
            conversation_id="conv-001",
            event_type="user_message",
            role="user",
            content_snippet="Open the Baseball Bat sample.",
            db_path=db,
        )
        rows = _query_all(db, ConversationEvent)
        assert len(rows) == 1
        assert rows[0].role == "user"
        assert rows[0].event_type == "user_message"

    def test_inserts_assistant_message(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_conversation_event(
            conversation_id="conv-002",
            event_type="assistant_message",
            role="assistant",
            content_snippet="I will open the model and inspect...",
            run_id="run-001",
            db_path=db,
        )
        rows = _query_all(db, ConversationEvent)
        assert rows[0].role == "assistant"
        assert rows[0].run_id == "run-001"

    def test_inserts_tool_call_event(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_conversation_event(
            conversation_id="conv-003",
            event_type="tool_call",
            content_snippet="list_features(...)",
            role="system",
            metadata_json='{"tool_name": "list_features", "status": "initiated"}',
            run_id="run-002",
            db_path=db,
        )
        rows = _query_all(db, ConversationEvent)
        event = rows[0]
        assert event.event_type == "tool_call"
        assert event.metadata_json is not None

    def test_multiple_events_same_conversation(self, tmp_path: Path):
        db = _db(tmp_path)
        for i in range(3):
            insert_conversation_event(
                conversation_id="conv-004",
                event_type="user_message" if i % 2 == 0 else "assistant_message",
                role="user" if i % 2 == 0 else "assistant",
                content_snippet=f"Message {i}",
                run_id=f"run-{i}",
                db_path=db,
            )
        rows = _query_all(db, ConversationEvent)
        assert len(rows) == 3
        assert all(row.conversation_id == "conv-004" for row in rows)

    def test_created_at_is_set(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_conversation_event(
            conversation_id="conv-005",
            event_type="user_message",
            role="user",
            content_snippet="test",
            db_path=db,
        )
        rows = _query_all(db, ConversationEvent)
        assert rows[0].created_at is not None
        assert "T" in rows[0].created_at


class TestFindConversationEvents:
    def test_retrieves_events_for_conversation(self, tmp_path: Path):
        db = _db(tmp_path)
        for i in range(3):
            insert_conversation_event(
                conversation_id="conv-timeline",
                event_type="user_message",
                role="user",
                content_snippet=f"Message {i}",
                db_path=db,
            )
        result = find_conversation_events("conv-timeline", db_path=db)
        assert len(result) == 3

    def test_returns_empty_for_missing_conversation(self, tmp_path: Path):
        db = _db(tmp_path)
        result = find_conversation_events("nonexistent-conv", db_path=db)
        assert result == []

    def test_ordered_by_creation_time(self, tmp_path: Path):
        db = _db(tmp_path)
        conversations = ["conv-A", "conv-B", "conv-A"]  # A, B, A
        for i, conv_id in enumerate(conversations):
            insert_conversation_event(
                conversation_id=conv_id,
                event_type="user_message",
                role="user",
                content_snippet=f"Event {i}",
                db_path=db,
            )

        result_a = find_conversation_events("conv-A", db_path=db)
        snippets = [e["content_snippet"] for e in result_a]
        assert snippets == ["Event 0", "Event 2"]

    def test_returns_all_fields(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_conversation_event(
            conversation_id="conv-fields",
            event_type="tool_call",
            role="system",
            content_snippet="Tool: classify_feature_tree",
            run_id="run-classify",
            metadata_json='{"status": "success"}',
            db_path=db,
        )
        result = find_conversation_events("conv-fields", db_path=db)
        event = result[0]
        for key in (
            "id",
            "conversation_id",
            "run_id",
            "event_type",
            "role",
            "content_snippet",
            "metadata_json",
            "created_at",
        ):
            assert key in event


class TestFindRunTimeline:
    def test_reconstructs_run_timeline(self, tmp_path: Path):
        db = _db(tmp_path)

        # Insert a run
        insert_run(
            run_id="timeline-run-001",
            agent_name="print-architect.agent.md",
            prompt="Design a bracket.",
            status="success",
            output_json=None,
            model_name="github:openai/gpt-4.1",
            db_path=db,
        )

        # Insert tool events
        insert_tool_event(
            run_id="timeline-run-001",
            tool_name="create_part",
            phase="pre",
            payload_json='{"name": "bracket"}',
            db_path=db,
        )
        insert_tool_event(
            run_id="timeline-run-001",
            tool_name="create_part",
            phase="post",
            payload_json=None,
            db_path=db,
        )

        # Insert conversation events
        insert_conversation_event(
            conversation_id="conv-001",
            run_id="timeline-run-001",
            event_type="user_message",
            role="user",
            content_snippet="Build a bracket.",
            db_path=db,
        )

        timeline = find_run_timeline("timeline-run-001", db_path=db)

        assert timeline["run_id"] == "timeline-run-001"
        assert timeline["run_info"] is not None
        assert timeline["run_info"]["agent_name"] == "print-architect.agent.md"
        assert len(timeline["events"]) >= 3  # 2 tool + 1 message

    def test_timeline_events_sorted_chronologically(self, tmp_path: Path):
        db = _db(tmp_path)

        insert_run(
            run_id="timeline-sort-test",
            agent_name="agent.md",
            prompt="Test",
            status="success",
            output_json=None,
            model_name=None,
            db_path=db,
        )

        # Insert events in non-chronological order (by DB insertion)
        insert_conversation_event(
            conversation_id="conv-sort",
            run_id="timeline-sort-test",
            event_type="assistant_message",
            role="assistant",
            content_snippet="Message 2",
            db_path=db,
        )
        insert_tool_event(
            run_id="timeline-sort-test",
            tool_name="tool1",
            phase="pre",
            payload_json=None,
            db_path=db,
        )
        insert_conversation_event(
            conversation_id="conv-sort",
            run_id="timeline-sort-test",
            event_type="user_message",
            role="user",
            content_snippet="Message 1",
            db_path=db,
        )

        timeline = find_run_timeline("timeline-sort-test", db_path=db)
        events = timeline["events"]

        # Verify all timestamps are in increasing order
        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps)

    def test_timeline_with_empty_run(self, tmp_path: Path):
        db = _db(tmp_path)

        insert_run(
            run_id="empty-run",
            agent_name="agent.md",
            prompt="Test",
            status="success",
            output_json=None,
            model_name=None,
            db_path=db,
        )

        timeline = find_run_timeline("empty-run", db_path=db)
        assert timeline["run_id"] == "empty-run"
        assert timeline["run_info"] is not None
        assert timeline["events"] == []

    def test_timeline_for_nonexistent_run(self, tmp_path: Path):
        db = _db(tmp_path)

        timeline = find_run_timeline("nonexistent-run", db_path=db)
        assert timeline["run_id"] == "nonexistent-run"
        assert timeline["run_info"] is None
        assert timeline["events"] == []
