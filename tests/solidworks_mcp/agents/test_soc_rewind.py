"""Tests for soc_rewind.py — all pure Python, no SolidWorks required."""

from __future__ import annotations

import pytest

from solidworks_mcp.agents.soc_rewind import (
    _cli,
    parse_script_checkpoints,
    rewind_to_checkpoint,
    truncate_script_at,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SCRIPT_HEADER = """\
from __future__ import annotations

import asyncio


async def build_part() -> None:
    config = load_config()
    adapter = await create_adapter(config)
    await adapter.connect()
    try:
"""

_SCRIPT_FOOTER = """\
    finally:
        await adapter.disconnect()


if __name__ == "__main__":
    asyncio.run(build_part())
"""

_CHECKPOINT_BLOCK = """\
        # -- checkpoint ────────────────────────────────────────
        # label:    base-extrude
        # file:     C:/tmp/checkpoint_base.sldprt
        # records:  1-5
        # ────────────────────────────────────────────────────────
"""

_CHECKPOINT_BLOCK_2 = """\
        # -- checkpoint ────────────────────────────────────────
        # label:    after-cut
        # file:     C:/tmp/checkpoint_cut.sldprt
        # records:  6-10
        # ────────────────────────────────────────────────────────
"""


def _make_script(*body_chunks: str) -> str:
    body = "".join(body_chunks)
    return _SCRIPT_HEADER + body + "\n" + _SCRIPT_FOOTER


# ---------------------------------------------------------------------------
# parse_script_checkpoints
# ---------------------------------------------------------------------------


def test_parse_no_checkpoints():
    script = _make_script(
        "        require(await adapter.create_part(name='p'), 'create_part')\n"
    )
    result = parse_script_checkpoints(script)
    assert result == []


def test_parse_one_checkpoint():
    script = _make_script(
        "        require(await adapter.create_part(name='p'), 'create_part')\n",
        _CHECKPOINT_BLOCK,
    )
    result = parse_script_checkpoints(script)
    assert len(result) == 1
    assert result[0]["label"] == "base-extrude"
    assert result[0]["file"] == "C:/tmp/checkpoint_base.sldprt"
    assert "line_start" in result[0]
    assert "line_end" in result[0]
    assert result[0]["line_start"] < result[0]["line_end"]


def test_parse_two_checkpoints():
    script = _make_script(
        "        require(await adapter.create_part(name='p'), 'create_part')\n",
        _CHECKPOINT_BLOCK,
        "        require(await adapter.create_extrusion(depth=10), 'extrude')\n",
        _CHECKPOINT_BLOCK_2,
    )
    result = parse_script_checkpoints(script)
    assert len(result) == 2
    assert result[0]["label"] == "base-extrude"
    assert result[1]["label"] == "after-cut"
    # Checkpoints should be in order
    assert result[0]["line_start"] < result[1]["line_start"]


def test_parse_checkpoint_label_stripped():
    script = _make_script(_CHECKPOINT_BLOCK)
    result = parse_script_checkpoints(script)
    assert result[0]["label"] == "base-extrude"


def test_parse_checkpoint_file_stripped():
    script = _make_script(_CHECKPOINT_BLOCK)
    result = parse_script_checkpoints(script)
    assert result[0]["file"] == "C:/tmp/checkpoint_base.sldprt"


# ---------------------------------------------------------------------------
# truncate_script_at
# ---------------------------------------------------------------------------


def test_truncate_basic():
    script = _make_script(
        "        require(await adapter.create_part(name='p'), 'create_part')\n",
        _CHECKPOINT_BLOCK,
        "        require(await adapter.create_sketch('Front'), 'create_sketch')\n",
    )
    truncated = truncate_script_at(script, "base-extrude")
    # The truncated script must contain the checkpoint block
    assert "# label:    base-extrude" in truncated
    # Must NOT contain the create_sketch call that came after
    assert "create_sketch" not in truncated


def test_truncate_adds_footer_if_absent():
    # Build a script with no footer (simulate mid-body truncation)
    script = (
        _SCRIPT_HEADER
        + "        require(await adapter.create_part(name='p'), 'create_part')\n"
    )
    script += _CHECKPOINT_BLOCK
    # No footer
    truncated = truncate_script_at(script, "base-extrude")
    assert "await adapter.disconnect()" in truncated
    assert "asyncio.run(build_part())" in truncated


def test_truncate_preserves_disconnect_if_already_present():
    script = _make_script(
        _CHECKPOINT_BLOCK,
    )
    truncated = truncate_script_at(script, "base-extrude")
    # Should not duplicate the disconnect
    assert truncated.count("await adapter.disconnect()") == 1


def test_truncate_unknown_label_raises_key_error():
    script = _make_script(_CHECKPOINT_BLOCK)
    with pytest.raises(KeyError, match="no-such-label"):
        truncate_script_at(script, "no-such-label")


def test_truncate_key_error_lists_available():
    script = _make_script(_CHECKPOINT_BLOCK)
    with pytest.raises(KeyError) as exc_info:
        truncate_script_at(script, "wrong-label")
    assert "base-extrude" in str(exc_info.value)


def test_truncate_at_first_of_two_checkpoints():
    script = _make_script(
        "        require(await adapter.create_part(name='p'), 'create_part')\n",
        _CHECKPOINT_BLOCK,
        "        require(await adapter.create_extrusion(depth=10), 'extrude')\n",
        _CHECKPOINT_BLOCK_2,
    )
    truncated = truncate_script_at(script, "base-extrude")
    assert "base-extrude" in truncated
    assert "after-cut" not in truncated
    assert "create_extrusion" not in truncated


def test_truncate_at_second_of_two_checkpoints():
    script = _make_script(
        "        require(await adapter.create_part(name='p'), 'create_part')\n",
        _CHECKPOINT_BLOCK,
        "        require(await adapter.create_extrusion(depth=10), 'extrude')\n",
        _CHECKPOINT_BLOCK_2,
    )
    truncated = truncate_script_at(script, "after-cut")
    assert "base-extrude" in truncated
    assert "after-cut" in truncated
    assert "create_extrusion" in truncated


def test_truncate_result_is_runnable_python(tmp_path):
    script = _make_script(
        "        require(await adapter.create_part(name='p'), 'create_part')\n",
        _CHECKPOINT_BLOCK,
    )
    truncated = truncate_script_at(script, "base-extrude")
    # Must be syntactically valid Python
    import ast

    ast.parse(truncated)  # raises SyntaxError if not valid


# ---------------------------------------------------------------------------
# list_checkpoints (DB-backed) — uses a real temp SQLite db
# ---------------------------------------------------------------------------


def test_list_checkpoints_empty(tmp_path):
    from solidworks_mcp.agents.history_db import init_db
    from solidworks_mcp.agents.soc_rewind import list_checkpoints

    db = tmp_path / "test.sqlite3"
    init_db(db)
    result = list_checkpoints("no-such-session", db_path=db)
    assert result == []


def test_list_checkpoints_returns_entries(tmp_path):
    from solidworks_mcp.agents.history_db import init_db
    from solidworks_mcp.agents.soc_rewind import list_checkpoints

    db = tmp_path / "test.sqlite3"
    init_db(db)

    # Insert a SoCCheckpoint via the DB directly
    from sqlmodel import Session

    from solidworks_mcp.agents.history_db import SoCCheckpoint, _build_engine

    engine = _build_engine(db)
    with Session(engine) as sess:
        sess.add(
            SoCCheckpoint(
                session_id="sess-chk",
                label="my-checkpoint",
                file_path="C:/tmp/cp.sldprt",
                first_record_id=1,
                last_record_id=3,
                created_at="2026-01-01T00:00:00",
            )
        )
        sess.commit()

    result = list_checkpoints("sess-chk", db_path=db)
    assert len(result) == 1
    assert result[0]["label"] == "my-checkpoint"
    assert result[0]["file_path"] == "C:/tmp/cp.sldprt"


# ---------------------------------------------------------------------------
# rewind_to_checkpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rewind_to_checkpoint_missing_cp_raises(monkeypatch):
    """Missing checkpoints should raise a clear error."""
    # Ensure the DB lookup failure path raises RuntimeError.
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.get_soc_checkpoint",
        lambda *_a, **_kw: None,
    )

    with pytest.raises(RuntimeError, match="not found"):
        await rewind_to_checkpoint(adapter=None, session_id="s1", label="missing")


@pytest.mark.asyncio
async def test_rewind_to_checkpoint_open_model_failure(monkeypatch):
    """Adapter open failures should raise RuntimeError."""
    # Provide a checkpoint but simulate adapter failure.
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.get_soc_checkpoint",
        lambda *_a, **_kw: {"file_path": "C:/tmp/checkpoint.sldprt"},
    )

    class _Adapter:
        async def open_model(self, _path):
            return type("Result", (), {"is_success": False, "error": "boom"})()

    with pytest.raises(RuntimeError, match="Failed to open"):
        await rewind_to_checkpoint(_Adapter(), session_id="s1", label="cp")


@pytest.mark.asyncio
async def test_rewind_to_checkpoint_returns_truncated_script(monkeypatch):
    """Truncation should return the script up to the checkpoint."""
    # Validate the happy-path truncation with an in-script checkpoint.
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.get_soc_checkpoint",
        lambda *_a, **_kw: {"file_path": "C:/tmp/checkpoint.sldprt"},
    )

    class _Adapter:
        async def open_model(self, _path):
            return type("Result", (), {"is_success": True, "error": ""})()

    script = _make_script(_CHECKPOINT_BLOCK)
    truncated = await rewind_to_checkpoint(
        _Adapter(), session_id="s1", label="base-extrude", script_text=script
    )
    assert "# label:    base-extrude" in truncated


@pytest.mark.asyncio
async def test_rewind_to_checkpoint_returns_original_when_label_missing(monkeypatch):
    """Missing checkpoint blocks should return the original script."""
    # Validate the KeyError fallback path.
    monkeypatch.setattr(
        "solidworks_mcp.agents.history_db.get_soc_checkpoint",
        lambda *_a, **_kw: {"file_path": "C:/tmp/checkpoint.sldprt"},
    )

    class _Adapter:
        async def open_model(self, _path):
            return type("Result", (), {"is_success": True, "error": ""})()

    script = _make_script("        # no checkpoint block here\n")
    truncated = await rewind_to_checkpoint(
        _Adapter(), session_id="s1", label="missing", script_text=script
    )
    assert truncated == script


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_usage_requires_args(monkeypatch, capsys):
    """CLI should print usage when args are missing."""
    # Trigger the usage guard by providing too few args.
    monkeypatch.setattr("sys.argv", ["soc_rewind.py"])
    with pytest.raises(SystemExit):
        _cli()
    out = capsys.readouterr().out
    assert "Usage: python -m solidworks_mcp.agents.soc_rewind" in out


def test_cli_missing_label_prints_available(monkeypatch, capsys):
    """CLI should print available labels on mismatch."""
    # Provide a label that does not exist and assert available labels are printed.
    monkeypatch.setattr("sys.argv", ["soc_rewind.py", "s1", "missing"])
    monkeypatch.setattr(
        "solidworks_mcp.agents.soc_rewind.list_checkpoints",
        lambda *_a, **_kw: [
            {
                "label": "base",
                "file_path": "x",
                "first_record_id": 1,
                "last_record_id": 2,
                "created_at": "now",
            }
        ],
    )
    with pytest.raises(SystemExit):
        _cli()
    out = capsys.readouterr().out
    assert "not found" in out
    assert "base" in out


def test_cli_prints_checkpoint_info(monkeypatch, capsys):
    """CLI should print checkpoint metadata when found."""
    # Provide a matching label and assert printed fields.
    monkeypatch.setattr("sys.argv", ["soc_rewind.py", "s1", "base"])
    monkeypatch.setattr(
        "solidworks_mcp.agents.soc_rewind.list_checkpoints",
        lambda *_a, **_kw: [
            {
                "label": "base",
                "file_path": "x",
                "first_record_id": 1,
                "last_record_id": 2,
                "created_at": "now",
            }
        ],
    )
    _cli()
    out = capsys.readouterr().out
    assert "Checkpoint: base" in out
    assert "file:" in out
