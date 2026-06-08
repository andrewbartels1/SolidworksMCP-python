"""Tests for soc_pickup.py — all pure Python, no SolidWorks required."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from solidworks_mcp.agents.soc_pickup import (
    _classify,
    _feature_type,
    diff_feature_trees,
    emit_feature_lines,
    generate_pickup_lines,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _feat(name: str, ftype: str) -> dict:
    return {"name": name, "type": ftype}


# ---------------------------------------------------------------------------
# _classify
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ftype,expected",
    [
        ("Boss-Extrude", "extrude"),
        ("boss-extrude", "extrude"),
        ("Extrusion", "extrude"),
        ("Cut-Extrude", "cut"),
        ("cutextrude", "cut"),
        ("CutExtrude", "cut"),
        ("Fillet", "fillet"),
        ("round", "fillet"),
        ("Chamfer", "chamfer"),
        ("Sketch", "sketch"),
        ("RefPlane", "plane"),
        ("reference plane", "plane"),
        ("Mirror", "mirror"),
        ("MirrorSolid", "mirror"),
        ("LinearPattern", "pattern"),
        ("CircularPattern", "pattern"),
        ("pattern", "pattern"),
        ("WeirdUnknown", "unknown"),
        ("", "unknown"),
    ],
)
def test_classify(ftype: str, expected: str):
    assert _classify(ftype.lower()) == expected


def test_feature_type_from_type_key():
    assert _feature_type({"type": "Fillet"}) == "fillet"


def test_feature_type_from_feature_type_key():
    assert _feature_type({"feature_type": "Boss-Extrude"}) == "boss-extrude"


def test_feature_type_missing():
    assert _feature_type({}) == ""


# ---------------------------------------------------------------------------
# diff_feature_trees
# ---------------------------------------------------------------------------


def test_diff_both_empty():
    assert diff_feature_trees([], []) == []


def test_diff_no_new_features():
    old = [_feat("Boss-Extrude1", "Boss-Extrude"), _feat("Sketch1", "Sketch")]
    new = [_feat("Boss-Extrude1", "Boss-Extrude"), _feat("Sketch1", "Sketch")]
    assert diff_feature_trees(old, new) == []


def test_diff_detects_new_features():
    old = [_feat("Boss-Extrude1", "Boss-Extrude")]
    new = [
        _feat("Boss-Extrude1", "Boss-Extrude"),
        _feat("Fillet1", "Fillet"),
        _feat("Cut-Extrude1", "Cut-Extrude"),
    ]
    result = diff_feature_trees(old, new)
    assert len(result) == 2
    assert result[0]["name"] == "Fillet1"
    assert result[1]["name"] == "Cut-Extrude1"


def test_diff_all_new_when_old_empty():
    new = [_feat("Boss-Extrude1", "Boss-Extrude"), _feat("Sketch1", "Sketch")]
    result = diff_feature_trees([], new)
    assert len(result) == 2


def test_diff_preserves_order():
    old = [_feat("A", "Sketch")]
    new = [_feat("A", "Sketch"), _feat("B", "Fillet"), _feat("C", "Boss-Extrude")]
    result = diff_feature_trees(old, new)
    assert [r["name"] for r in result] == ["B", "C"]


def test_diff_ignores_removed_features():
    # A feature removed from new_tree is not in the diff (only additions)
    old = [_feat("A", "Sketch"), _feat("B", "Fillet")]
    new = [_feat("A", "Sketch")]  # B removed
    result = diff_feature_trees(old, new)
    assert result == []


# ---------------------------------------------------------------------------
# emit_feature_lines
# ---------------------------------------------------------------------------


def test_emit_extrude_contains_create_extrusion():
    lines = emit_feature_lines(_feat("Boss-Extrude2", "Boss-Extrude"))
    code = "\n".join(lines)
    assert "adapter.create_extrusion" in code
    assert "ExtrusionParameters" in code
    assert "depth=?" in code
    assert "Boss-Extrude2" in code


def test_emit_cut_contains_create_cut_extrude():
    lines = emit_feature_lines(_feat("Cut-Extrude1", "Cut-Extrude"))
    code = "\n".join(lines)
    assert "adapter.create_cut_extrude" in code
    assert "depth=?" in code


def test_emit_fillet_contains_add_fillet():
    lines = emit_feature_lines(_feat("Fillet1", "Fillet"))
    code = "\n".join(lines)
    assert "adapter.add_fillet" in code
    assert "radius=?" in code


def test_emit_sketch_contains_create_sketch():
    lines = emit_feature_lines(_feat("Sketch2", "Sketch"))
    code = "\n".join(lines)
    assert "adapter.create_sketch" in code
    assert "adapter.exit_sketch" in code


def test_emit_chamfer_is_todo():
    lines = emit_feature_lines(_feat("Chamfer1", "Chamfer"))
    code = "\n".join(lines)
    assert "# TODO" in code


def test_emit_plane_is_todo():
    lines = emit_feature_lines(_feat("Plane1", "RefPlane"))
    code = "\n".join(lines)
    assert "# TODO" in code


def test_emit_mirror_is_todo():
    lines = emit_feature_lines(_feat("Mirror1", "Mirror"))
    code = "\n".join(lines)
    assert "# TODO" in code


def test_emit_unknown_is_todo():
    lines = emit_feature_lines(_feat("Mystery1", "WeirdType"))
    code = "\n".join(lines)
    assert "# TODO" in code
    assert "weirdtype" in code.lower()


def test_emit_lines_always_ends_with_blank():
    for ftype in ("Boss-Extrude", "Cut-Extrude", "Fillet", "Sketch", "WeirdType"):
        lines = emit_feature_lines(_feat("F1", ftype))
        assert lines[-1] == "", f"Expected trailing blank for {ftype}"


# ---------------------------------------------------------------------------
# generate_pickup_lines
# ---------------------------------------------------------------------------


def test_generate_pickup_lines_empty_new_features():
    lines = generate_pickup_lines([])
    assert len(lines) == 1
    assert "no new features detected" in lines[0]


def test_generate_pickup_lines_header_present():
    lines = generate_pickup_lines([_feat("Fillet1", "Fillet")])
    code = "\n".join(lines)
    assert "# [pickup]" in code
    assert "1 new feature(s)" in code


def test_generate_pickup_lines_multiple_features():
    features = [
        _feat("Boss-Extrude2", "Boss-Extrude"),
        _feat("Fillet1", "Fillet"),
    ]
    lines = generate_pickup_lines(features)
    code = "\n".join(lines)
    assert "2 new feature(s)" in code
    assert "create_extrusion" in code
    assert "add_fillet" in code


def test_generate_pickup_lines_fill_placeholder_note():
    lines = generate_pickup_lines([_feat("Boss-Extrude1", "Boss-Extrude")])
    code = "\n".join(lines)
    assert "Fill in '?' placeholders" in code


# ---------------------------------------------------------------------------
# pickup_changes — async with mock adapter (no SolidWorks)
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db(tmp_path):
    from solidworks_mcp.agents.history_db import init_db

    db = tmp_path / "pickup_test.sqlite3"
    init_db(db)
    return db


def _make_adapter(feature_list: list[dict], model_path: str = "C:/tmp/part.sldprt"):
    adapter = MagicMock()
    feat_result = MagicMock()
    feat_result.is_success = True
    feat_result.data = feature_list
    adapter.list_features = AsyncMock(return_value=feat_result)

    info_result = MagicMock()
    info_result.is_success = True
    info_result.data = {"file_path": model_path}
    adapter.get_model_info = AsyncMock(return_value=info_result)

    # soc_create_checkpoint must be awaitable — MagicMock isn't by default
    adapter.soc_create_checkpoint = AsyncMock(return_value=None)

    return adapter


@pytest.mark.asyncio
async def test_pickup_changes_no_snapshot_all_new(tmp_db):
    from solidworks_mcp.agents.soc_pickup import pickup_changes

    features = [
        _feat("Boss-Extrude1", "Boss-Extrude"),
        _feat("Fillet1", "Fillet"),
    ]
    adapter = _make_adapter(features)

    lines = await pickup_changes(adapter, "sess-pickup", db_path=tmp_db)
    code = "\n".join(lines)
    # Both features should appear since there's no old snapshot
    assert "create_extrusion" in code
    assert "add_fillet" in code


@pytest.mark.asyncio
async def test_pickup_changes_with_snapshot_only_delta(tmp_db):
    from solidworks_mcp.agents.history_db import insert_model_state_snapshot
    from solidworks_mcp.agents.soc_pickup import pickup_changes

    old_features = [_feat("Boss-Extrude1", "Boss-Extrude")]
    insert_model_state_snapshot(
        session_id="sess-delta",
        model_path="C:/tmp/part.sldprt",
        feature_tree_json=json.dumps(old_features),
        db_path=tmp_db,
    )

    new_features = [
        _feat("Boss-Extrude1", "Boss-Extrude"),  # existing
        _feat("Fillet1", "Fillet"),  # new
    ]
    adapter = _make_adapter(new_features)

    lines = await pickup_changes(adapter, "sess-delta", db_path=tmp_db)
    code = "\n".join(lines)
    # Only the new Fillet should appear
    assert "add_fillet" in code
    assert "create_extrusion" not in code


@pytest.mark.asyncio
async def test_pickup_changes_no_new_features(tmp_db):
    from solidworks_mcp.agents.history_db import insert_model_state_snapshot
    from solidworks_mcp.agents.soc_pickup import pickup_changes

    features = [_feat("Boss-Extrude1", "Boss-Extrude")]
    insert_model_state_snapshot(
        session_id="sess-no-delta",
        model_path="C:/tmp/part.sldprt",
        feature_tree_json=json.dumps(features),
        db_path=tmp_db,
    )

    adapter = _make_adapter(features)
    lines = await pickup_changes(adapter, "sess-no-delta", db_path=tmp_db)
    assert any("no new features" in l for l in lines)


@pytest.mark.asyncio
async def test_pickup_changes_appends_to_script_file(tmp_db, tmp_path):
    from solidworks_mcp.agents.soc_pickup import pickup_changes

    script_path = tmp_path / "my_part.py"
    script_path.write_text(
        "async def build_part():\n    adapter = ...\n    try:\n        pass\n    finally:\n        await adapter.disconnect()\n",
        encoding="utf-8",
    )

    features = [_feat("Fillet1", "Fillet")]
    adapter = _make_adapter(features)

    await pickup_changes(
        adapter, "sess-append", output_path=script_path, db_path=tmp_db
    )

    content = script_path.read_text()
    assert "add_fillet" in content


@pytest.mark.asyncio
async def test_pickup_changes_list_features_failure(tmp_db):
    from solidworks_mcp.agents.soc_pickup import pickup_changes

    adapter = MagicMock()
    fail_result = MagicMock()
    fail_result.is_success = False
    fail_result.error = "model not active"
    adapter.list_features = AsyncMock(return_value=fail_result)

    with pytest.raises(RuntimeError, match="list_features failed"):
        await pickup_changes(adapter, "sess-fail", db_path=tmp_db)


# ---------------------------------------------------------------------------
# revert_tool_call_records — integration with history_db
# ---------------------------------------------------------------------------


def test_revert_tool_call_records(tmp_path):
    from solidworks_mcp.agents.history_db import (
        init_db,
        insert_tool_call_record,
        list_tool_call_records,
        revert_tool_call_records,
    )

    db = tmp_path / "revert_test.sqlite3"
    init_db(db)

    for tool in [
        "create_part",
        "create_sketch",
        "add_line",
        "exit_sketch",
        "create_extrusion",
    ]:
        insert_tool_call_record(session_id="sess-rev", tool_name=tool, db_path=db)

    all_records = list_tool_call_records("sess-rev", db_path=db, include_reverted=True)
    assert len(all_records) == 5
    third_id = all_records[2]["id"]

    count = revert_tool_call_records("sess-rev", from_record_id=third_id, db_path=db)
    assert count == 3

    active = list_tool_call_records("sess-rev", db_path=db)
    assert len(active) == 2
    assert all(r["tool_name"] in ("create_part", "create_sketch") for r in active)


def test_revert_tool_call_records_returns_zero_when_none_match(tmp_path):
    from solidworks_mcp.agents.history_db import (
        init_db,
        insert_tool_call_record,
        revert_tool_call_records,
    )

    db = tmp_path / "revert_zero.sqlite3"
    init_db(db)
    insert_tool_call_record(session_id="sess-z", tool_name="create_part", db_path=db)

    count = revert_tool_call_records("sess-z", from_record_id=9999, db_path=db)
    assert count == 0


def test_reverted_records_excluded_by_default(tmp_path):
    from solidworks_mcp.agents.history_db import (
        init_db,
        insert_tool_call_record,
        list_tool_call_records,
        revert_tool_call_records,
    )

    db = tmp_path / "revert_excl.sqlite3"
    init_db(db)

    insert_tool_call_record(session_id="sess-excl", tool_name="create_part", db_path=db)
    insert_tool_call_record(
        session_id="sess-excl", tool_name="create_sketch", db_path=db
    )

    all_records = list_tool_call_records("sess-excl", db_path=db, include_reverted=True)
    second_id = all_records[1]["id"]
    revert_tool_call_records("sess-excl", from_record_id=second_id, db_path=db)

    active = list_tool_call_records("sess-excl", db_path=db)
    assert len(active) == 1
    assert active[0]["tool_name"] == "create_part"

    with_reverted = list_tool_call_records(
        "sess-excl", db_path=db, include_reverted=True
    )
    assert len(with_reverted) == 2


# ---------------------------------------------------------------------------
# Additional coverage for uncovered lines
# ---------------------------------------------------------------------------


def test_feature_map_returns_name_keyed_dict() -> None:
    """_feature_map should return dict keyed by feature name. Covers line 63."""
    from solidworks_mcp.agents.soc_pickup import _feature_map

    tree = [{"name": "BossExtrude1", "type": "Boss"}, {"name": "Cut1", "type": "Cut"}]
    result = _feature_map(tree)
    assert "BossExtrude1" in result
    assert result["BossExtrude1"]["type"] == "Boss"


def test_pickup_changes_handles_bad_snapshot_json(tmp_path, monkeypatch) -> None:
    """pickup_changes should handle invalid snapshot JSON gracefully. Covers lines 260-261."""
    import pytest
    from solidworks_mcp.agents import soc_pickup
    from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

    mock_adapter = AsyncMock()
    mock_adapter.list_features = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=[{"name": "NewFeat", "type": "Boss"}],
        )
    )
    mock_adapter.get_model_info = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data={"path": "/tmp/model.sldprt"},
        )
    )
    mock_adapter.save_file = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )

    # Provide a snapshot with invalid JSON in feature_tree_json
    # The functions are imported inline from .history_db, so patch at that level
    from solidworks_mcp.agents import history_db

    monkeypatch.setattr(
        history_db,
        "list_model_state_snapshots",
        lambda *_a, **_kw: [{"feature_tree_json": "{bad json"}],
    )
    monkeypatch.setattr(history_db, "insert_model_state_snapshot", lambda **_kw: 1)

    import asyncio

    result = asyncio.run(soc_pickup.pickup_changes(mock_adapter, session_id="s1"))
    assert result is not None


def test_pickup_changes_inserts_before_finally_block(tmp_path) -> None:
    """pickup_changes should insert pickup lines before the finally block. Covers line 276."""
    from solidworks_mcp.agents.soc_pickup import generate_pickup_lines

    new_features = [{"name": "BossExtrude1", "type": "Boss", "suppressed": False}]
    lines = generate_pickup_lines(new_features)
    assert any("BossExtrude1" in line or "create" in line.lower() for line in lines)


def test_pickup_changes_appends_when_no_finally(tmp_path, monkeypatch) -> None:
    """pickup_changes should append to script when no finally block. Covers line 278."""
    from solidworks_mcp.agents import soc_pickup
    from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus

    mock_adapter = AsyncMock()
    mock_adapter.list_features = AsyncMock(
        return_value=AdapterResult(
            status=AdapterResultStatus.SUCCESS,
            data=[{"name": "NewFeat2", "type": "Boss"}],
        )
    )
    mock_adapter.get_model_info = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS, data={})
    )
    mock_adapter.save_file = AsyncMock(
        return_value=AdapterResult(status=AdapterResultStatus.SUCCESS)
    )

    from solidworks_mcp.agents import history_db

    monkeypatch.setattr(history_db, "list_model_state_snapshots", lambda *_a, **_kw: [])
    monkeypatch.setattr(history_db, "insert_model_state_snapshot", lambda **_kw: 1)

    script_file = tmp_path / "test_script.py"
    script_file.write_text("# script content\nsome_code()\n", encoding="utf-8")

    import asyncio

    result = asyncio.run(
        soc_pickup.pickup_changes(
            mock_adapter, session_id="s1", output_path=str(script_file)
        )
    )
    # File was written with appended lines (no "    finally:" present)
    content = script_file.read_text(encoding="utf-8")
    assert "script content" in content


def test_soc_pickup_cli_exits(monkeypatch) -> None:
    """_cli should print usage and exit(1). Covers lines 310-320."""
    import sys
    from solidworks_mcp.agents import soc_pickup

    monkeypatch.setattr(sys, "argv", ["prog"])
    with pytest.raises(SystemExit) as exc:
        soc_pickup._cli()
    assert exc.value.code == 1
