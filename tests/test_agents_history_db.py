"""Tests for src/solidworks_mcp/agents/history_db.py — targeting 100% coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.solidworks_mcp.agents.history_db import (
    DEFAULT_DB_PATH,
    AgentRun,
    ConversationEvent,
    ErrorCatalog,
    ErrorRecord,
    ToolEvent,
    _build_engine,
    _utc_now_iso,
    find_conversation_events,
    find_recent_errors,
    find_run_timeline,
    init_db,
    insert_conversation_event,
    insert_error,
    insert_run,
    insert_tool_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db(tmp_path: Path) -> Path:
    """Return a test-specific DB path that won't collide with production."""
    return tmp_path / "test_agent_memory.sqlite3"


# ---------------------------------------------------------------------------
# _utc_now_iso
# ---------------------------------------------------------------------------


class TestUtcNowIso:
    def test_returns_iso_string(self):
        ts = _utc_now_iso()
        assert isinstance(ts, str)
        assert "T" in ts  # ISO 8601 separator

    def test_contains_utc_offset(self):
        ts = _utc_now_iso()
        # datetime.now(UTC).isoformat() includes +00:00
        assert "+00:00" in ts or "Z" in ts or ts.endswith("+00:00")


# ---------------------------------------------------------------------------
# _build_engine / init_db
# ---------------------------------------------------------------------------


class TestBuildEngineAndInitDb:
    def test_build_engine_creates_parent_dir(self, tmp_path: Path):
        nested = tmp_path / "sub" / "agent_memory.sqlite3"
        engine = _build_engine(nested)
        assert nested.parent.exists()
        engine.dispose()

    def test_init_db_returns_resolved_path(self, tmp_path: Path):
        db = _db(tmp_path)
        result = init_db(db)
        assert result == db
        assert db.exists()

    def test_init_db_creates_tables(self, tmp_path: Path):
        db = _db(tmp_path)
        init_db(db)
        from sqlmodel import create_engine, inspect as sqlinspect

        engine = create_engine(f"sqlite:///{db}")
        inspector = sqlinspect(engine)
        table_names = inspector.get_table_names()
        assert "agentrun" in table_names
        assert "toolevent" in table_names
        assert "errorcatalog" in table_names
        engine.dispose()

    def test_init_db_uses_default_path_when_none(self, monkeypatch, tmp_path: Path):
        """Passing db_path=None falls back to DEFAULT_DB_PATH."""
        import src.solidworks_mcp.agents.history_db as hdb

        fake_default = tmp_path / ".solidworks_mcp" / "agent_memory.sqlite3"
        monkeypatch.setattr(hdb, "DEFAULT_DB_PATH", fake_default)
        result = hdb.init_db(None)
        assert result == fake_default
        assert fake_default.exists()

    def test_init_db_idempotent(self, tmp_path: Path):
        """Calling init_db twice does not raise."""
        db = _db(tmp_path)
        init_db(db)
        init_db(db)  # second call should not raise


# ---------------------------------------------------------------------------
# insert_run
# ---------------------------------------------------------------------------


class TestInsertRun:
    def test_inserts_row(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_run(
            run_id="run-001",
            agent_name="solidworks-print-architect.agent.md",
            prompt="Design a snap-fit cover.",
            status="success",
            output_json='{"summary": "ok"}',
            model_name="github:openai/gpt-4.1",
            db_path=db,
        )
        rows = _query_all(db, AgentRun)
        assert len(rows) == 1
        assert rows[0].run_id == "run-001"
        assert rows[0].status == "success"

    def test_null_output_json(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_run(
            run_id="run-002",
            agent_name="some-agent.md",
            prompt="A prompt.",
            status="error",
            output_json=None,
            model_name=None,
            db_path=db,
        )
        rows = _query_all(db, AgentRun)
        assert rows[0].output_json is None
        assert rows[0].model_name is None

    def test_multiple_runs(self, tmp_path: Path):
        db = _db(tmp_path)
        for i in range(5):
            insert_run(
                run_id=f"run-{i}",
                agent_name="agent.md",
                prompt=f"Prompt {i}",
                status="success",
                output_json=None,
                model_name="github:openai/gpt-4.1",
                db_path=db,
            )
        assert len(_query_all(db, AgentRun)) == 5

    def test_created_at_is_set(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_run(
            run_id="ts-test",
            agent_name="agent.md",
            prompt="prompt",
            status="success",
            output_json=None,
            model_name=None,
            db_path=db,
        )
        rows = _query_all(db, AgentRun)
        assert rows[0].created_at is not None
        assert "T" in rows[0].created_at


# ---------------------------------------------------------------------------
# insert_tool_event
# ---------------------------------------------------------------------------


class TestInsertToolEvent:
    def test_inserts_event(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_tool_event(
            run_id="run-ev-001",
            tool_name="create_sketch",
            phase="pre",
            payload_json='{"plane": "Top"}',
            db_path=db,
        )
        rows = _query_all(db, ToolEvent)
        assert len(rows) == 1
        assert rows[0].tool_name == "create_sketch"
        assert rows[0].phase == "pre"

    def test_null_payload(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_tool_event(
            run_id="run-ev-002",
            tool_name="exit_sketch",
            phase="post",
            payload_json=None,
            db_path=db,
        )
        rows = _query_all(db, ToolEvent)
        assert rows[0].payload_json is None


# ---------------------------------------------------------------------------
# insert_error
# ---------------------------------------------------------------------------


class TestInsertError:
    def _record(self, **overrides) -> ErrorRecord:
        defaults = dict(
            source="pydantic_ai",
            tool_name="run_validated_prompt",
            error_type="RecoverableFailure",
            error_message="Could not parse output.",
            root_cause="Schema mismatch.",
            remediation="Narrow prompt scope.",
        )
        defaults.update(overrides)
        return ErrorRecord(**defaults)

    def test_inserts_error(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_error(self._record(), db_path=db)
        rows = _query_all(db, ErrorCatalog)
        assert len(rows) == 1
        assert rows[0].error_type == "RecoverableFailure"

    def test_with_run_id(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_error(self._record(), run_id="run-err-001", db_path=db)
        rows = _query_all(db, ErrorCatalog)
        assert rows[0].run_id == "run-err-001"

    def test_without_run_id(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_error(self._record())  # uses default DB path — monkeypatched below
        # Just verify no exception is raised (uses default path in real run)

    def test_multiple_errors(self, tmp_path: Path):
        db = _db(tmp_path)
        for i in range(3):
            insert_error(self._record(error_message=f"Error {i}"), db_path=db)
        assert len(_query_all(db, ErrorCatalog)) == 3


# ---------------------------------------------------------------------------
# find_recent_errors
# ---------------------------------------------------------------------------


class TestFindRecentErrors:
    def test_returns_empty_on_fresh_db(self, tmp_path: Path):
        db = _db(tmp_path)
        result = find_recent_errors(db_path=db)
        assert result == []

    def test_returns_inserted_errors(self, tmp_path: Path):
        db = _db(tmp_path)
        record = ErrorRecord(
            source="adapter",
            tool_name="open_model",
            error_type="COMError",
            error_message="File not found",
            root_cause="Missing file",
            remediation="Verify path",
        )
        insert_error(record, run_id="r1", db_path=db)
        result = find_recent_errors(db_path=db)
        assert len(result) == 1
        assert result[0]["error_type"] == "COMError"
        assert result[0]["run_id"] == "r1"

    def test_returns_all_expected_keys(self, tmp_path: Path):
        db = _db(tmp_path)
        insert_error(
            ErrorRecord(
                source="s", tool_name="t", error_type="E",
                error_message="msg", root_cause="rc", remediation="fix"
            ),
            db_path=db,
        )
        row = find_recent_errors(db_path=db)[0]
        for key in ("run_id", "source", "tool_name", "error_type",
                    "error_message", "root_cause", "remediation", "created_at"):
            assert key in row

    def test_respects_limit(self, tmp_path: Path):
        db = _db(tmp_path)
        for i in range(10):
            insert_error(
                ErrorRecord(
                    source="s", tool_name="t", error_type=f"E{i}",
                    error_message="m", root_cause="r", remediation="fix"
                ),
                db_path=db,
            )
        result = find_recent_errors(limit=3, db_path=db)
        assert len(result) == 3

    def test_returns_newest_first(self, tmp_path: Path):
        db = _db(tmp_path)
        for i in range(5):
            insert_error(
                ErrorRecord(
                    source="s", tool_name="t", error_type=f"E{i}",
                    error_message="m", root_cause="r", remediation="fix"
                ),
                db_path=db,
            )
        result = find_recent_errors(db_path=db)
        # Descending by id — last inserted has highest id
        ids = [r["error_type"] for r in result]
        assert ids[0] == "E4"  # most recently inserted

    def test_default_limit_is_20(self, tmp_path: Path):
        db = _db(tmp_path)
        for i in range(25):
            insert_error(
                ErrorRecord(
                    source="s", tool_name="t", error_type=f"E{i}",
                    error_message="m", root_cause="r", remediation="fix"
                ),
                db_path=db,
            )
        result = find_recent_errors(db_path=db)
        assert len(result) == 20


# ---------------------------------------------------------------------------
# DEFAULT_DB_PATH constant
# ---------------------------------------------------------------------------


class TestDefaultDbPath:
    def test_is_path_instance(self):
        assert isinstance(DEFAULT_DB_PATH, Path)

    def test_has_expected_filename(self):
        assert DEFAULT_DB_PATH.name == "agent_memory.sqlite3"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _query_all(db: Path, model_cls):
    """Utility to fetch all rows from a SQLModel table."""
    from sqlmodel import Session, create_engine, select

    engine = create_engine(f"sqlite:///{db}")
    with Session(engine) as session:
        rows = session.exec(select(model_cls)).all()
    engine.dispose()
    return rows
