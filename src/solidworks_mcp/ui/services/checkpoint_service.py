"""Checkpoint execution service for the Prefab CAD assistant dashboard.

Responsible for planning and executing individual checkpoint steps against the
SolidWorks adapter.

Design note:
    ``_run_checkpoint_tools`` uses a handler map to dispatch tool names to adapter
    calls, allowing new tool bindings without growing a long conditional chain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from ...adapters import create_adapter
from ...adapters.base import ExtrusionParameters
from ...config import load_config
from ...agents.history_db import (
    insert_tool_call_record,
    list_plan_checkpoints,
    update_plan_checkpoint,
    upsert_design_session,
)
from ._utils import (
    DEFAULT_SESSION_ID,
    DEFAULT_SOURCE_MODE,
    DEFAULT_USER_GOAL,
    parse_json_blob,
    merge_metadata,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _planned_tools(planned: dict[str, Any]) -> list[str]:
    """Return the list of tool names from a planned-action dict.

    Args:
        planned: Parsed planned-action JSON dict.

    Returns:
        List of tool name strings.
    """
    tools = planned.get("tools", [])
    return [str(t) for t in tools] if isinstance(tools, list) else []


# TODO: Tasks pending completion -@andre at 5/4/2026, 8:53:10 PM
#  Implement this in pydantic or something? Seems like it shouldn't be here.
def _planned_float(planned: dict[str, Any], key: str, default: float) -> float:
    """Read a float from planned payload with a safe fallback."""
    value = planned.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _run_checkpoint_tools(
    planned: dict[str, Any],
) -> dict[str, Any]:
    """Execute the tools listed in a planned-action dict against the SolidWorks adapter.

    Unsupported tools are marked as MOCKED rather than failing the entire checkpoint.

    Args:
        planned: Parsed planned-action JSON dict containing a ``tools`` list.

    Returns:
        Dict with keys ``tool_runs``, ``mocked_tools``, and ``failed_tools``.

    Note:
        Tool execution uses a strategy-style handler map.
    """
    config = load_config()
    adapter = await create_adapter(config)
    tool_runs: list[dict[str, Any]] = []
    mocked_tools: list[str] = []
    failed_tools: list[str] = []
    ensured_part_document = False

    async def _ensure_part_document() -> bool:
        nonlocal ensured_part_document
        if ensured_part_document:
            return True

        if not hasattr(adapter, "get_model_info"):
            ensured_part_document = True
            return True

        model_info = await adapter.get_model_info()
        has_active_model = bool(model_info.is_success and model_info.data)
        if has_active_model:
            ensured_part_document = True
            return True

        if not hasattr(adapter, "create_part"):
            ensured_part_document = True
            return True

        create_part_result = await adapter.create_part(name="ui_checkpoint_part")
        create_part_success = bool(create_part_result.is_success)
        tool_runs.append(
            {
                "tool": "create_part",
                "status": "success" if create_part_success else "error",
                "message": (
                    "Created blank part document for checkpoint execution"
                    if create_part_success
                    else str(create_part_result.error or "create_part failed")
                ),
            }
        )
        if not create_part_success:
            failed_tools.append("create_part")
            return False

        ensured_part_document = True
        return True

    def _record_result(
        tool_name: str, success: bool, success_message: str, error: Any
    ) -> None:
        tool_runs.append(
            {
                "tool": tool_name,
                "status": "success" if success else "error",
                "message": success_message
                if success
                else str(error or f"{tool_name} failed"),
            }
        )
        if not success:
            failed_tools.append(tool_name)

    async def _run_create_sketch() -> None:
        if not await _ensure_part_document():
            return
        sketch_plane = str(planned.get("sketch_plane") or "Top")
        result = await adapter.create_sketch(sketch_plane)
        _record_result(
            "create_sketch",
            bool(result.is_success),
            f"Created sketch on {sketch_plane} plane",
            result.error,
        )

    async def _run_add_line() -> None:
        if not await _ensure_part_document():
            return
        profile = str(planned.get("profile") or "line").lower()
        if profile == "closed_rect":
            width = _planned_float(planned, "rect_width_mm", 40.0)
            height = _planned_float(planned, "rect_height_mm", 24.0)
            segments = [
                (0.0, 0.0, width, 0.0),
                (width, 0.0, width, height),
                (width, height, 0.0, height),
                (0.0, height, 0.0, 0.0),
            ]
            failed = False
            for x1, y1, x2, y2 in segments:
                result = await adapter.add_line(x1, y1, x2, y2)
                if not result.is_success:
                    failed = True
                    _record_result(
                        "add_line",
                        False,
                        "",
                        result.error,
                    )
                    break
            if not failed:
                _record_result(
                    "add_line",
                    True,
                    f"Added closed rectangular profile {width}x{height} mm",
                    None,
                )
            return

        result = await adapter.add_line(0.0, 0.0, 40.0, 0.0)
        _record_result(
            "add_line",
            bool(result.is_success),
            "Added baseline line segment",
            result.error,
        )

    async def _run_add_circle() -> None:
        if not await _ensure_part_document():
            return
        center = planned.get("circle_center_mm")
        if isinstance(center, list) and len(center) == 2:
            x = _planned_float({"x": center[0]}, "x", 20.0)
            y = _planned_float({"y": center[1]}, "y", 12.0)
        else:
            x, y = 20.0, 12.0
        radius = _planned_float(planned, "circle_radius_mm", 4.0)
        result = await adapter.add_circle(x, y, radius)
        _record_result(
            "add_circle",
            bool(result.is_success),
            f"Added circle profile at ({x}, {y}) with radius {radius} mm",
            result.error,
        )

    async def _run_exit_sketch() -> None:
        result = await adapter.exit_sketch()
        _record_result(
            "exit_sketch",
            bool(result.is_success),
            "Exited active sketch",
            result.error,
        )

    async def _run_create_extrusion() -> None:
        if not await _ensure_part_document():
            return

        prepare_profile = str(planned.get("prepare_profile") or "").lower()
        if prepare_profile == "closed_rect":
            sketch_plane = str(planned.get("sketch_plane") or "Top")
            sketch_result = await adapter.create_sketch(sketch_plane)
            if not sketch_result.is_success:
                _record_result(
                    "create_extrusion",
                    False,
                    "",
                    sketch_result.error,
                )
                return

            width = _planned_float(planned, "rect_width_mm", 40.0)
            height = _planned_float(planned, "rect_height_mm", 24.0)
            segments = [
                (0.0, 0.0, width, 0.0),
                (width, 0.0, width, height),
                (width, height, 0.0, height),
                (0.0, height, 0.0, 0.0),
            ]
            for x1, y1, x2, y2 in segments:
                line_result = await adapter.add_line(x1, y1, x2, y2)
                if not line_result.is_success:
                    _record_result(
                        "create_extrusion",
                        False,
                        "",
                        line_result.error,
                    )
                    return

            exit_result = await adapter.exit_sketch()
            if not exit_result.is_success:
                _record_result(
                    "create_extrusion",
                    False,
                    "",
                    exit_result.error,
                )
                return

        depth_mm = _planned_float(planned, "depth_mm", 10.0)
        result = await adapter.create_extrusion(ExtrusionParameters(depth=depth_mm))
        _record_result(
            "create_extrusion",
            bool(result.is_success),
            f"Created {depth_mm}mm extrusion",
            result.error,
        )

    async def _run_create_cut() -> None:
        depth_mm = _planned_float(planned, "depth_mm", 3.0)
        if not await _ensure_part_document():
            return

        result = None

        if bool(planned.get("prepare_base_extrusion")):
            width = _planned_float(planned, "rect_width_mm", 40.0)
            height = _planned_float(planned, "rect_height_mm", 24.0)
            base_depth_mm = _planned_float(planned, "base_depth_mm", 10.0)
            sketch_plane = str(planned.get("sketch_plane") or "Top")

            base_sketch = await adapter.create_sketch(sketch_plane)
            if not base_sketch.is_success:
                _record_result("create_cut", False, "", base_sketch.error)
                return

            for x1, y1, x2, y2 in (
                (0.0, 0.0, width, 0.0),
                (width, 0.0, width, height),
                (width, height, 0.0, height),
                (0.0, height, 0.0, 0.0),
            ):
                line_result = await adapter.add_line(x1, y1, x2, y2)
                if not line_result.is_success:
                    _record_result("create_cut", False, "", line_result.error)
                    return

            base_exit = await adapter.exit_sketch()
            if not base_exit.is_success:
                _record_result("create_cut", False, "", base_exit.error)
                return

            base_extrude = await adapter.create_extrusion(
                ExtrusionParameters(depth=base_depth_mm)
            )
            if not base_extrude.is_success:
                _record_result("create_cut", False, "", base_extrude.error)
                return

        prepare_profile = str(planned.get("prepare_profile") or "").lower()
        if prepare_profile == "circle":
            sketch_plane = str(planned.get("sketch_plane") or "Top")
            sketch_result = await adapter.create_sketch(sketch_plane)
            if not sketch_result.is_success:
                _record_result("create_cut", False, "", sketch_result.error)
                return

            center = planned.get("circle_center_mm")
            if isinstance(center, list) and len(center) == 2:
                x = _planned_float({"x": center[0]}, "x", 20.0)
                y = _planned_float({"y": center[1]}, "y", 12.0)
            else:
                x, y = 20.0, 12.0
            radius = _planned_float(planned, "circle_radius_mm", 4.0)
            circle_result = await adapter.add_circle(x, y, radius)
            if not circle_result.is_success:
                _record_result("create_cut", False, "", circle_result.error)
                return

            exit_result = await adapter.exit_sketch()
            if not exit_result.is_success:
                _record_result("create_cut", False, "", exit_result.error)
                return
            sketch_name = str(planned.get("sketch_name") or "Sketch1")
            if hasattr(adapter, "create_cut"):
                result = await adapter.create_cut(sketch_name, depth_mm)
            else:
                result = await adapter.create_cut_extrude(
                    ExtrusionParameters(depth=depth_mm)
                )
        else:
            if hasattr(adapter, "create_cut"):
                sketch_name = str(planned.get("sketch_name") or "Sketch1")
                result = await adapter.create_cut(sketch_name, depth_mm)
            else:
                result = await adapter.create_cut_extrude(
                    ExtrusionParameters(depth=depth_mm)
                )

        if result is None:
            _record_result("create_cut", False, "", "create_cut was not executed")
            return

        _record_result(
            "create_cut",
            bool(result.is_success),
            f"Created {depth_mm}mm cut feature",
            result.error,
        )

    async def _run_open_model() -> None:
        candidate_path = str(planned.get("model_path") or "").strip()
        if not candidate_path:
            mocked_tools.append("open_model")
            tool_runs.append(
                {
                    "tool": "open_model",
                    "status": "mocked",
                    "message": "MOCKED: open_model requires planned.model_path",
                }
            )
            return
        result = await adapter.open_model(candidate_path)
        _record_result(
            "open_model", bool(result.is_success), "Opened model", result.error
        )

    async def _run_get_model_info() -> None:
        result = await adapter.get_model_info()
        _record_result(
            "get_model_info",
            bool(result.is_success),
            "Fetched model metadata",
            result.error,
        )

    async def _run_list_features() -> None:
        result = await adapter.list_features(include_suppressed=True)
        _record_result(
            "list_features",
            bool(result.is_success),
            "Listed model features",
            result.error,
        )

    async def _run_create_part() -> None:
        result = await adapter.create_part(name="ui_checkpoint_part")
        _record_result(
            "create_part",
            bool(result.is_success),
            "Created part document",
            result.error,
        )

    async def _run_create_assembly() -> None:
        result = await adapter.create_assembly(name="UJoint")
        _record_result(
            "create_assembly",
            bool(result.is_success),
            "Created assembly document",
            result.error,
        )

    async def _run_export_image() -> None:
        mocked_tools.append("export_image")
        tool_runs.append(
            {
                "tool": "export_image",
                "status": "mocked",
                "message": "MOCKED: export_image requires a resolved output path in planned action",
            }
        )

    async def _run_check_interference() -> None:
        mocked_tools.append("check_interference")
        tool_runs.append(
            {
                "tool": "check_interference",
                "status": "mocked",
                "message": "MOCKED: Requires tool-layer check_interference wiring.",
            }
        )

    handlers: dict[str, Any] = {
        "create_sketch": _run_create_sketch,
        "add_line": _run_add_line,
        "add_circle": _run_add_circle,
        "exit_sketch": _run_exit_sketch,
        "create_extrusion": _run_create_extrusion,
        "create_cut": _run_create_cut,
        "open_model": _run_open_model,
        "get_model_info": _run_get_model_info,
        "list_features": _run_list_features,
        "create_part": _run_create_part,
        "create_assembly": _run_create_assembly,
        "export_image": _run_export_image,
        "check_interference": _run_check_interference,
    }

    try:
        await adapter.connect()
        for tool_name in _planned_tools(planned):
            handler = handlers.get(tool_name)
            if handler is None:
                mocked_tools.append(tool_name)
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "status": "mocked",
                        "message": "MOCKED: No adapter binding defined for this tool.",
                    }
                )
                continue
            await handler()
    except Exception as exc:
        failed_tools.append("checkpoint.execute")
        tool_runs.append(
            {
                "tool": "checkpoint.execute",
                "status": "error",
                "message": str(exc),
            }
        )
    finally:
        try:
            await adapter.disconnect()
        except Exception:
            logger.debug("Adapter disconnect failed during checkpoint cleanup")

    return {
        "tool_runs": tool_runs,
        "mocked_tools": mocked_tools,
        "failed_tools": failed_tools,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def execute_next_checkpoint(
    session_id: str = DEFAULT_SESSION_ID,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Find and execute the next un-executed checkpoint in the session plan.

    Args:
        session_id: Dashboard session identifier.
        db_path: Optional SQLite path override.

    Returns:
        Full dashboard state payload.
    """
    from .session_service import build_dashboard_state, ensure_dashboard_session  # noqa: PLC0415

    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    checkpoints = list_plan_checkpoints(session_id, db_path=db_path)
    target = next((row for row in checkpoints if not row["executed"]), None)
    if target is None:
        merge_metadata(
            session_id,
            db_path=db_path,
            latest_message="All checkpoints have already been executed.",
        )
        return build_dashboard_state(session_id, db_path=db_path)

    planned = parse_json_blob(target["planned_action_json"])
    run_summary = await _run_checkpoint_tools(planned)
    failed_tools = run_summary["failed_tools"]
    mocked_tools = run_summary["mocked_tools"]
    tool_runs = run_summary["tool_runs"]
    executed = not failed_tools

    if failed_tools:
        message = (
            f"Checkpoint {target['checkpoint_index']} failed on tools: "
            f"{', '.join(failed_tools)}."
        )
    elif mocked_tools:
        message = (
            f"Executed checkpoint {target['checkpoint_index']} with MOCKED tools: "
            f"{', '.join(mocked_tools)}."
        )
    else:
        message = (
            f"Executed checkpoint {target['checkpoint_index']}: {target['title']}."
        )

    result_json = json.dumps(
        {
            "status": "success" if executed else "error",
            "message": message,
            "tools": _planned_tools(planned),
            "tool_runs": tool_runs,
            "mocked_tools": mocked_tools,
            "failed_tools": failed_tools,
        },
        ensure_ascii=True,
    )
    update_plan_checkpoint(
        int(target["id"]),
        approved_by_user=True,
        executed=executed,
        result_json=result_json,
        db_path=db_path,
    )

    for tool_run in tool_runs:
        insert_tool_call_record(
            session_id=session_id,
            checkpoint_id=int(target["id"]),
            tool_name=tool_run["tool"],
            input_json=json.dumps(planned, ensure_ascii=True),
            output_json=json.dumps(tool_run, ensure_ascii=True),
            success=tool_run["status"] == "success",
            db_path=db_path,
        )

    upsert_design_session(
        session_id=session_id,
        user_goal=session_row.get("user_goal") or DEFAULT_USER_GOAL,
        source_mode=session_row.get("source_mode") or DEFAULT_SOURCE_MODE,
        accepted_family=session_row.get("accepted_family"),
        status="executing" if executed else "error",
        current_checkpoint_index=(
            target["checkpoint_index"]
            if executed
            else session_row.get("current_checkpoint_index") or 0
        ),
        metadata_json=session_row.get("metadata_json"),
        db_path=db_path,
    )
    merge_metadata(
        session_id,
        db_path=db_path,
        latest_message=message,
        mocked_tools=mocked_tools,
        latest_error_text=(message if failed_tools else ""),
        remediation_hint=(
            "Review tool availability, then retry this checkpoint or inspect more evidence."
            if failed_tools
            else ""
        ),
    )
    return build_dashboard_state(session_id, db_path=db_path)
