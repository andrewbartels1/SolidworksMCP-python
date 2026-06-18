"""Checkpoint execution service for the Prefab CAD assistant dashboard.

Responsible for planning and executing individual checkpoint steps against the
SolidWorks adapter.

Design note:
    ``_run_checkpoint_tools`` uses a handler map to dispatch tool names to adapter
    calls, allowing new tool bindings without growing a long conditional chain.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any

from ...adapters import create_adapter
from ...agents.history_db import (
    insert_tool_call_record,
    list_plan_checkpoints,
    update_plan_checkpoint,
    upsert_design_session,
)
from ...config import load_config
from ._utils import (
    DEFAULT_API_ORIGIN,
    DEFAULT_PREVIEW_ORIENTATION,
    DEFAULT_SESSION_ID,
    DEFAULT_SOURCE_MODE,
    DEFAULT_USER_GOAL,
    ensure_preview_dir,
    merge_metadata,
    parse_json_blob,
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


def _checkpoint_script_dir(session_id: str) -> Path:
    return Path(".solidworks_mcp") / "checkpoint_scripts" / session_id


def _checkpoint_script_path(session_id: str, checkpoint_index: int) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    script_name = f"checkpoint_{checkpoint_index:03d}_{stamp}.py"
    return _checkpoint_script_dir(session_id) / script_name


def _planned_tool_payloads(planned: dict[str, Any], tool: str) -> list[dict[str, Any]]:
    """Return ordered payload dicts for a tool from planned action JSON.

    Supports either flat payloads (top-level keys) or nested execution-style
    payloads stored under ``tool`` and ``tool#N`` keys.
    """
    payloads: list[dict[str, Any]] = []
    direct = planned.get(tool)
    if isinstance(direct, dict):
        payloads.append(dict(direct))

    suffixed: list[tuple[str, dict[str, Any]]] = []
    for key, value in planned.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        if key.startswith(f"{tool}#"):
            suffixed.append((key, dict(value)))

    def _suffix_order(item: tuple[str, dict[str, Any]]) -> tuple[int, str]:
        key = item[0]
        suffix = key.split("#", 1)[1] if "#" in key else ""
        return (int(suffix) if suffix.isdigit() else 10_000, key)

    for _, payload in sorted(suffixed, key=_suffix_order):
        payloads.append(payload)

    return payloads


def _should_open_empty_part(
    session_meta: dict[str, Any], planned: dict[str, Any]
) -> bool:
    """Return whether checkpoint execution should open a blank part first."""
    workflow_mode = str(session_meta.get("workflow_mode") or "").strip().lower()
    if workflow_mode != "new_design":
        return False

    if str(session_meta.get("active_model_path") or "").strip():
        return False

    if bool(session_meta.get("new_design_part_opened")):
        return False

    tools = _planned_tools(planned)
    return not any(
        tool in {"create_part", "create_assembly", "open_model"} for tool in tools
    )


async def _open_empty_part_before_checkpoint(
    *,
    session_id: str,
    session_row: dict[str, Any],
    db_path: Path | None,
    api_origin: str,
) -> dict[str, Any]:
    """Create a blank part document and refresh preview before checkpoint execution."""
    from .preview_service import refresh_preview  # noqa: PLC0415

    config = load_config()
    adapter = await create_adapter(config)
    part_name = f"{session_id}_new_part"
    try:
        await adapter.connect()
        create_result = await adapter.create_part(name=part_name)
        if not getattr(create_result, "is_success", False):
            raise RuntimeError(create_result.error or "Failed to open blank part")

        merge_metadata(
            session_id,
            db_path=db_path,
            workflow_mode="new_design",
            new_design_part_opened=True,
            new_design_part_name=part_name,
            active_model_status="Opened a new empty part document for checkpoint execution.",
            active_model_type="Part",
            active_model_configuration="Default",
            preview_status="Refreshing preview for new empty part...",
            latest_message="Opened a new empty part document for checkpoint execution.",
            latest_error_text="",
            remediation_hint="",
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.open_empty_part",
            input_json=json.dumps(
                {
                    "session_id": session_id,
                    "part_name": part_name,
                    "user_goal": session_row.get("user_goal") or DEFAULT_USER_GOAL,
                },
                ensure_ascii=True,
            ),
            output_json=json.dumps(
                {"part_name": part_name, "status": "success"},
                ensure_ascii=True,
            ),
            success=True,
            db_path=db_path,
        )

        try:
            await refresh_preview(
                session_id,
                orientation=DEFAULT_PREVIEW_ORIENTATION,
                db_path=db_path,
                preview_dir=ensure_preview_dir(),
                api_origin=api_origin,
                adapter_override=adapter,
                active_model_path_override="",
                reopen_active_model=False,
            )
        except Exception as preview_exc:
            merge_metadata(
                session_id,
                db_path=db_path,
                latest_message="Opened a new empty part document; preview refresh is still pending.",
                preview_status="Opened a new empty part document; preview refresh is still pending.",
                latest_error_text=str(preview_exc),
                remediation_hint="Retry preview refresh after SolidWorks finishes opening the new part.",
            )
    finally:
        try:
            await adapter.disconnect()
        except Exception:
            pass

    return {"part_name": part_name, "status": "success"}


def _render_checkpoint_script(
    planned: dict[str, Any],
    *,
    session_id: str,
    checkpoint_index: int,
    checkpoint_title: str,
) -> str:
    """Render a strict script for checkpoint execution.

    The generated script has explicit breakpoint comments and does not use default
    geometry fallbacks. Missing parameters raise errors so users can repair the plan.
    """
    planned_json = json.dumps(planned, ensure_ascii=True)
    return dedent(
        f"""
        from __future__ import annotations

        import asyncio
        import json
        import os
        import pdb
        import traceback
        from typing import Any

        from solidworks_mcp.adapters import create_adapter
        from solidworks_mcp.adapters.base import ExtrusionParameters
        from solidworks_mcp.config import load_config

        SESSION_ID = {session_id!r}
        CHECKPOINT_INDEX = {checkpoint_index}
        CHECKPOINT_TITLE = {checkpoint_title!r}
        PLANNED: dict[str, Any] = json.loads({planned_json!r})
        DEBUG_PAUSE = os.getenv("SOLIDWORKS_UI_CHECKPOINT_DEBUG_PAUSE", "0").strip().lower() in {"1", "true", "yes", "on"}


        def require_key(key: str) -> Any:
            if key not in PLANNED:
                raise ValueError(f"Missing required planned key: {{key}}")
            return PLANNED[key]


        def require_float(key: str) -> float:
            value = require_key(key)
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid numeric value for {{key}}: {{value!r}}") from exc


        def require_first_float(*keys: str) -> float:
            for key in keys:
                if key in PLANNED:
                    try:
                        return float(PLANNED[key])
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            f"Invalid numeric value for {{key}}: {{PLANNED[key]!r}}"
                        ) from exc
            raise ValueError(f"Missing required planned key(s): {{', '.join(keys)}}")


        def require_vec(key: str, size: int) -> list[float]:
            raw = require_key(key)
            if not isinstance(raw, list) or len(raw) != size:
                raise ValueError(
                    f"{{key}} must be a list with {{size}} numeric values; got {{raw!r}}"
                )
            try:
                return [float(v) for v in raw]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{{key}} must contain numeric values; got {{raw!r}}") from exc


        def require_result(result: Any, label: str) -> Any:
            if result is None:
                raise RuntimeError(f"{{label}} returned None")
            if not getattr(result, "is_success", False):
                raise RuntimeError(f"{{label}} failed: {{getattr(result, 'error', 'unknown error')}}")
            return result


        def pause_point(label: str) -> None:
            print(f"EDIT POINT: {{label}}")
            if DEBUG_PAUSE:
                pdb.set_trace()


        def payloads_for_tool(tool: str) -> list[dict[str, Any]]:
            payloads: list[dict[str, Any]] = []
            direct = PLANNED.get(tool)
            if isinstance(direct, dict):
                payloads.append(dict(direct))

            suffixed: list[tuple[str, dict[str, Any]]] = []
            for key, value in PLANNED.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                if key.startswith(f"{{tool}}#"):
                    suffixed.append((key, dict(value)))

            def suffix_order(item: tuple[str, dict[str, Any]]) -> tuple[int, str]:
                key = item[0]
                suffix = key.split("#", 1)[1] if "#" in key else ""
                return (int(suffix) if suffix.isdigit() else 10_000, key)

            for _, payload in sorted(suffixed, key=suffix_order):
                payloads.append(payload)

            return payloads


        def key_from(payload: dict[str, Any], key: str) -> Any:
            if key in payload:
                return payload[key]
            return require_key(key)


        def vec_from(payload: dict[str, Any], key: str, size: int) -> list[float]:
            raw = key_from(payload, key)
            if not isinstance(raw, list) or len(raw) != size:
                raise ValueError(
                    f"{{key}} must be a list with {{size}} numeric values; got {{raw!r}}"
                )
            try:
                return [float(v) for v in raw]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{{key}} must contain numeric values; got {{raw!r}}") from exc


        def first_float_from(payload: dict[str, Any], *keys: str) -> float:
            for key in keys:
                if key in payload:
                    try:
                        return float(payload[key])
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"Invalid numeric value for {{key}}: {{payload[key]!r}}") from exc
            return require_first_float(*keys)


        async def run_checkpoint() -> dict[str, Any]:
            tools = PLANNED.get("tools", [])
            if not isinstance(tools, list) or not tools:
                raise ValueError("planned.tools must be a non-empty list")

            tool_runs: list[dict[str, str]] = []
            failed_tools: list[str] = []

            config = load_config()
            adapter = await create_adapter(config)

            await adapter.connect()
            try:
                for idx, tool in enumerate([str(t) for t in tools], start=1):
                    pause_point(f"checkpoint {{CHECKPOINT_INDEX}} step {{idx}}/{{len(tools)}} before {{tool}}")
                    print(f"CHECKPOINT {{CHECKPOINT_INDEX}} STEP {{idx}}/{{len(tools)}}: {{tool}}")
                    try:
                        if tool == "create_part":
                            payload = (payloads_for_tool(tool) or [{{}}])[0]
                            part_name = str(key_from(payload, "part_name"))
                            require_result(await adapter.create_part(name=part_name), "create_part")
                            tool_runs.append({{"tool": tool, "status": "success", "message": f"Created part '{{part_name}}'"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after create_part")

                        elif tool == "create_assembly":
                            payload = (payloads_for_tool(tool) or [{{}}])[0]
                            assembly_name = str(key_from(payload, "assembly_name"))
                            require_result(await adapter.create_assembly(name=assembly_name), "create_assembly")
                            tool_runs.append({{"tool": tool, "status": "success", "message": f"Created assembly '{{assembly_name}}'"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after create_assembly")

                        elif tool == "open_model":
                            payload = (payloads_for_tool(tool) or [{{}}])[0]
                            model_path = str(key_from(payload, "model_path"))
                            require_result(await adapter.open_model(model_path), "open_model")
                            tool_runs.append({{"tool": tool, "status": "success", "message": f"Opened model '{{model_path}}'"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after open_model")

                        elif tool == "create_sketch":
                            payloads = payloads_for_tool(tool) or [{{}}]
                            for payload in payloads:
                                sketch_plane = str(key_from(payload, "sketch_plane"))
                                require_result(await adapter.create_sketch(sketch_plane), "create_sketch")
                                tool_runs.append({{"tool": tool, "status": "success", "message": f"Created sketch on '{{sketch_plane}}'"}})
                                pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after create_sketch")

                        elif tool == "exit_sketch":
                            require_result(await adapter.exit_sketch(), "exit_sketch")
                            tool_runs.append({{"tool": tool, "status": "success", "message": "Exited sketch"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after exit_sketch")

                        elif tool == "add_line":
                            payloads = payloads_for_tool(tool) or [{{}}]
                            for payload in payloads:
                                if "line_mm" in payload or "line_mm" in PLANNED:
                                    x1, y1, x2, y2 = vec_from(payload, "line_mm", 4)
                                else:
                                    sx, sy = vec_from(payload, "line_start_mm", 2)
                                    ex, ey = vec_from(payload, "line_end_mm", 2)
                                    x1, y1, x2, y2 = sx, sy, ex, ey
                                require_result(await adapter.add_line(x1, y1, x2, y2), "add_line")
                                tool_runs.append({{"tool": tool, "status": "success", "message": "Added line"}})
                                pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after add_line")

                        elif tool == "add_rectangle":
                            payloads = payloads_for_tool(tool) or [{{}}]
                            for payload in payloads:
                                x, y, width, height = vec_from(payload, "rectangle_mm", 4)
                                require_result(await adapter.add_rectangle(x, y, width, height), "add_rectangle")
                                tool_runs.append({{"tool": tool, "status": "success", "message": "Added rectangle"}})
                                pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after add_rectangle")

                        elif tool == "add_circle":
                            payloads = payloads_for_tool(tool) or [{{}}]
                            for payload in payloads:
                                cx, cy = vec_from(payload, "circle_center_mm", 2)
                                radius = first_float_from(payload, "circle_radius_mm")
                                require_result(await adapter.add_circle(cx, cy, radius), "add_circle")
                                tool_runs.append({{"tool": tool, "status": "success", "message": "Added circle"}})
                                pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after add_circle")

                        elif tool == "add_centerline":
                            payloads = payloads_for_tool(tool) or [{{}}]
                            for payload in payloads:
                                x1, y1, x2, y2 = vec_from(payload, "centerline_mm", 4)
                                require_result(await adapter.add_centerline(x1, y1, x2, y2), "add_centerline")
                                tool_runs.append({{"tool": tool, "status": "success", "message": "Added centerline"}})
                                pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after add_centerline")

                        elif tool == "add_arc":
                            payloads = payloads_for_tool(tool) or [{{}}]
                            for payload in payloads:
                                cx, cy = vec_from(payload, "arc_center_mm", 2)
                                sx, sy = vec_from(payload, "arc_start_mm", 2)
                                ex, ey = vec_from(payload, "arc_end_mm", 2)
                                require_result(await adapter.add_arc(cx, cy, sx, sy, ex, ey), "add_arc")
                                tool_runs.append({{"tool": tool, "status": "success", "message": "Added arc"}})
                                pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after add_arc")

                        elif tool == "create_extrusion":
                            payload = (payloads_for_tool(tool) or [{{}}])[0]
                            depth = first_float_from(payload, "depth_mm", "depth")
                            params = ExtrusionParameters(
                                depth=depth,
                                thin_feature=bool(payload.get("thin_feature", PLANNED.get("thin_feature", False))),
                                thin_thickness=(
                                    float(payload["thin_thickness_mm"])
                                    if "thin_thickness_mm" in payload
                                    else (
                                        float(PLANNED["thin_thickness_mm"])
                                        if "thin_thickness_mm" in PLANNED
                                        else float(payload.get("thin_thickness", PLANNED.get("thin_thickness", 0.0)))
                                    )
                                ),
                                both_directions=bool(payload.get("both_directions", PLANNED.get("both_directions", False))),
                            )
                            require_result(await adapter.create_extrusion(params), "create_extrusion")
                            tool_runs.append({{"tool": tool, "status": "success", "message": f"Created extrusion depth={{depth}}mm"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after create_extrusion")

                        elif tool == "create_cut_extrude":
                            payload = (payloads_for_tool(tool) or [{{}}])[0]
                            depth = first_float_from(payload, "depth_mm", "depth")
                            params = ExtrusionParameters(depth=depth)
                            require_result(await adapter.create_cut_extrude(params), "create_cut_extrude")
                            tool_runs.append({{"tool": tool, "status": "success", "message": f"Created cut-extrude depth={{depth}}mm"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after create_cut_extrude")

                        elif tool == "create_cut":
                            payload = (payloads_for_tool(tool) or [{{}}])[0]
                            depth = first_float_from(payload, "depth_mm", "depth")
                            sketch_name = str(payload.get("sketch_name", PLANNED.get("sketch_name", "")))
                            if sketch_name:
                                require_result(await adapter.create_cut(sketch_name, depth), "create_cut")
                                tool_runs.append({{"tool": tool, "status": "success", "message": f"Created cut from {{sketch_name}} depth={{depth}}mm"}})
                            else:
                                params = ExtrusionParameters(depth=depth)
                                require_result(await adapter.create_cut_extrude(params), "create_cut")
                                tool_runs.append({{"tool": tool, "status": "success", "message": f"Created cut-extrude depth={{depth}}mm"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after create_cut")

                        elif tool == "add_fillet":
                            payload = (payloads_for_tool(tool) or [{{}}])[0]
                            radius = first_float_from(payload, "radius_mm", "radius")
                            raw_edges = payload.get("edge_names", PLANNED.get("edge_names", []))
                            edge_names = [str(edge) for edge in raw_edges] if isinstance(raw_edges, list) else []
                            require_result(await adapter.add_fillet(radius, edge_names), "add_fillet")
                            tool_runs.append({{"tool": tool, "status": "success", "message": f"Added fillet radius={{radius}}mm"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after add_fillet")

                        elif tool == "check_sketch_fully_defined":
                            payload = (payloads_for_tool(tool) or [{{}}])[0]
                            sketch_name = payload.get("sketch_name", PLANNED.get("sketch_name"))
                            require_result(
                                await adapter.check_sketch_fully_defined(
                                    str(sketch_name) if sketch_name else None
                                ),
                                "check_sketch_fully_defined",
                            )
                            tool_runs.append({{"tool": tool, "status": "success", "message": "Checked sketch definition"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after check_sketch_fully_defined")

                        elif tool == "save_file":
                            payload = (payloads_for_tool(tool) or [{{}}])[0]
                            file_path = str(key_from(payload, "file_path"))
                            require_result(await adapter.save_file(file_path), "save_file")
                            tool_runs.append({{"tool": tool, "status": "success", "message": f"Saved file '{{file_path}}'"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after save_file")

                        elif tool == "get_model_info":
                            require_result(await adapter.get_model_info(), "get_model_info")
                            tool_runs.append({{"tool": tool, "status": "success", "message": "Retrieved model info"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after get_model_info")

                        elif tool == "list_features":
                            require_result(
                                await adapter.list_features(include_suppressed=True),
                                "list_features",
                            )
                            tool_runs.append({{"tool": tool, "status": "success", "message": "Listed features"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after list_features")

                        elif tool == "get_mass_properties":
                            require_result(await adapter.get_mass_properties(), "get_mass_properties")
                            tool_runs.append({{"tool": tool, "status": "success", "message": "Retrieved mass properties"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after get_mass_properties")

                        elif tool == "analyze_geometry":
                            require_result(await adapter.get_model_info(), "analyze_geometry.get_model_info")
                            require_result(
                                await adapter.list_features(include_suppressed=True),
                                "analyze_geometry.list_features",
                            )
                            require_result(
                                await adapter.get_mass_properties(),
                                "analyze_geometry.get_mass_properties",
                            )
                            tool_runs.append({{"tool": tool, "status": "success", "message": "Geometry analysis completed"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after analyze_geometry")

                        elif tool == "export_image":
                            payloads = payloads_for_tool(tool)
                            payload = payloads[0] if payloads else PLANNED.get("export_image")
                            if payload is None:
                                payload = {{
                                    "file_path": require_key("file_path"),
                                    "format_type": require_key("format_type"),
                                }}
                                if "width" in PLANNED:
                                    payload["width"] = int(PLANNED["width"])
                                if "height" in PLANNED:
                                    payload["height"] = int(PLANNED["height"])
                                if "view_orientation" in PLANNED:
                                    payload["view_orientation"] = str(PLANNED["view_orientation"])
                            if not isinstance(payload, dict):
                                raise ValueError("export_image must be an object payload")
                            require_result(await adapter.export_image(payload), "export_image")
                            tool_runs.append({{"tool": tool, "status": "success", "message": "Exported image"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after export_image")

                        elif tool == "check_interference":
                            payload = require_key("check_interference")
                            if not isinstance(payload, dict):
                                raise ValueError("check_interference must be an object payload")
                            require_result(await adapter.check_interference(payload), "check_interference")
                            tool_runs.append({{"tool": tool, "status": "success", "message": "Checked interference"}})
                            pause_point(f"checkpoint {{CHECKPOINT_INDEX}} after check_interference")

                        else:
                            raise ValueError(f"Unsupported tool '{{tool}}' in strict script mode")

                    except Exception as step_exc:
                        failed_tools.append(tool)
                        tool_runs.append({{"tool": tool, "status": "error", "message": str(step_exc)}})
                        break

            finally:
                try:
                    await adapter.disconnect()
                except Exception:
                    pass

            return {{
                "tool_runs": tool_runs,
                "failed_tools": failed_tools,
            }}


        def main() -> int:
            try:
                summary = asyncio.run(run_checkpoint())
                print("CHECKPOINT_SCRIPT_RESULT::" + json.dumps(summary, ensure_ascii=True))
                return 0 if not summary.get("failed_tools") else 1
            except Exception as exc:
                summary = {{
                    "tool_runs": [
                        {{"tool": "checkpoint.script", "status": "error", "message": str(exc)}},
                        {{"tool": "checkpoint.script", "status": "error", "message": traceback.format_exc()}},
                    ],
                    "failed_tools": ["checkpoint.script"],
                }}
                print("CHECKPOINT_SCRIPT_RESULT::" + json.dumps(summary, ensure_ascii=True))
                return 1


        if __name__ == "__main__":
            raise SystemExit(main())
        """
    )


# ---------------------------------------------------------------------------
# Direct-execution helpers
# ---------------------------------------------------------------------------

_MOCKED_TOOLS: frozenset[str] = frozenset({"check_interference"})


def _pf(planned: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    """Return the first float-convertible value found under any of *keys*."""
    for key in keys:
        if key in planned:
            try:
                return float(planned[key])
            except (TypeError, ValueError):
                pass
    return default


def _pv(
    planned: dict[str, Any],
    *keys: str,
    size: int = 4,
    default: list[float] | None = None,
) -> list[float]:
    """Return a float list of *size* from the first matching key in planned."""
    for key in keys:
        val = planned.get(key)
        if isinstance(val, list) and len(val) == size:
            try:
                return [float(v) for v in val]
            except (TypeError, ValueError):
                pass
    return default if default is not None else [0.0] * size


async def _execute_tool(
    adapter: Any,
    planned: dict[str, Any],
    tool: str,
) -> dict[str, Any] | None:
    """Dispatch *tool* to the adapter using parameters from *planned*.

    Returns a tool_run dict on success, raises on failure, or returns None for
    unknown tools (caller treats None as mocked).
    Uses sensible defaults for any missing geometry parameters.
    """
    from ...adapters.base import ExtrusionParameters  # noqa: PLC0415

    tool_payloads = _planned_tool_payloads(planned, tool)
    ctx = dict(planned)

    def _ok(result: Any, label: str) -> None:
        if not getattr(result, "is_success", True):
            raise RuntimeError(getattr(result, "error", f"{label} failed"))

    if tool == "create_part":
        name = str(ctx.get("part_name", "untitled_part"))
        _ok(await adapter.create_part(name=name), "create_part")
        return {"tool": tool, "status": "success", "message": f"Created part '{name}'"}

    if tool == "create_assembly":
        name = str(ctx.get("assembly_name", "untitled_assembly"))
        _ok(await adapter.create_assembly(name=name), "create_assembly")
        return {
            "tool": tool,
            "status": "success",
            "message": f"Created assembly '{name}'",
        }

    if tool == "open_model":
        path = str(ctx.get("model_path", ""))
        if not path:
            raise ValueError("open_model requires model_path")
        _ok(await adapter.open_model(path), "open_model")
        return {"tool": tool, "status": "success", "message": f"Opened '{path}'"}

    if tool == "create_sketch":
        payloads = tool_payloads or [{}]
        plane = "Front"
        for payload in payloads:
            plane = str({**ctx, **payload}.get("sketch_plane", "Front"))
            _ok(await adapter.create_sketch(plane), "create_sketch")
        return {
            "tool": tool,
            "status": "success",
            "message": f"Created sketch on '{plane}'",
        }

    if tool == "exit_sketch":
        _ok(await adapter.exit_sketch(), "exit_sketch")
        return {"tool": tool, "status": "success", "message": "Exited sketch"}

    if tool == "add_line":
        payloads = tool_payloads or [{}]
        for payload in payloads:
            merged = {**ctx, **payload}
            if "line_mm" in merged:
                x1, y1, x2, y2 = _pv(merged, "line_mm", size=4, default=[0, 0, 10, 10])
            elif "line_start_mm" in merged:
                sx, sy = _pv(merged, "line_start_mm", size=2, default=[0, 0])
                ex, ey = _pv(merged, "line_end_mm", size=2, default=[10, 10])
                x1, y1, x2, y2 = sx, sy, ex, ey
            else:
                x1, y1, x2, y2 = 0.0, 0.0, 10.0, 10.0
            _ok(await adapter.add_line(x1, y1, x2, y2), "add_line")
        return {"tool": tool, "status": "success", "message": "Added line"}

    if tool == "add_rectangle":
        payloads = tool_payloads or [{}]
        for payload in payloads:
            merged = {**ctx, **payload}
            x, y, w, h = _pv(merged, "rectangle_mm", size=4, default=[0, 0, 50, 30])
            _ok(await adapter.add_rectangle(x, y, w, h), "add_rectangle")
        return {"tool": tool, "status": "success", "message": "Added rectangle"}

    if tool == "add_circle":
        payloads = tool_payloads or [{}]
        for payload in payloads:
            merged = {**ctx, **payload}
            cx, cy = _pv(merged, "circle_center_mm", size=2, default=[0, 0])
            radius = _pf(merged, "circle_radius_mm", default=5.0)
            _ok(await adapter.add_circle(cx, cy, radius), "add_circle")
        return {"tool": tool, "status": "success", "message": "Added circle"}

    if tool == "add_centerline":
        payloads = tool_payloads or [{}]
        for payload in payloads:
            merged = {**ctx, **payload}
            x1, y1, x2, y2 = _pv(merged, "centerline_mm", size=4, default=[0, 0, 0, 50])
            _ok(await adapter.add_centerline(x1, y1, x2, y2), "add_centerline")
        return {"tool": tool, "status": "success", "message": "Added centerline"}

    if tool == "add_arc":
        payloads = tool_payloads or [{}]
        for payload in payloads:
            merged = {**ctx, **payload}
            cx, cy = _pv(merged, "arc_center_mm", size=2, default=[0, 0])
            sx, sy = _pv(merged, "arc_start_mm", size=2, default=[10, 0])
            ex, ey = _pv(merged, "arc_end_mm", size=2, default=[0, 10])
            _ok(await adapter.add_arc(cx, cy, sx, sy, ex, ey), "add_arc")
        return {"tool": tool, "status": "success", "message": "Added arc"}

    if tool == "create_extrusion":
        payload = (tool_payloads or [{}])[0]
        merged = {**ctx, **payload}
        depth = _pf(merged, "depth_mm", "depth", default=10.0)
        params = ExtrusionParameters(
            depth=depth,
            thin_feature=bool(merged.get("thin_feature", False)),
            thin_thickness=float(
                merged.get("thin_thickness_mm", merged.get("thin_thickness", 0.0))
            ),
            both_directions=bool(merged.get("both_directions", False)),
        )
        _ok(await adapter.create_extrusion(params), "create_extrusion")
        return {
            "tool": tool,
            "status": "success",
            "message": f"Extrusion depth={depth}mm",
        }

    if tool == "create_cut_extrude":
        payload = (tool_payloads or [{}])[0]
        merged = {**ctx, **payload}
        depth = _pf(merged, "depth_mm", "depth", default=10.0)
        _ok(
            await adapter.create_cut_extrude(ExtrusionParameters(depth=depth)),
            "create_cut_extrude",
        )
        return {
            "tool": tool,
            "status": "success",
            "message": f"Cut-extrude depth={depth}mm",
        }

    if tool == "create_cut":
        payload = (tool_payloads or [{}])[0]
        merged = {**ctx, **payload}
        depth = _pf(merged, "depth_mm", "depth", default=10.0)
        sketch_name = str(merged.get("sketch_name", ""))
        if sketch_name:
            _ok(await adapter.create_cut(sketch_name, depth), "create_cut")
            return {
                "tool": tool,
                "status": "success",
                "message": f"Cut from {sketch_name} depth={depth}mm",
            }
        _ok(
            await adapter.create_cut_extrude(ExtrusionParameters(depth=depth)),
            "create_cut",
        )
        return {
            "tool": tool,
            "status": "success",
            "message": f"Cut-extrude depth={depth}mm",
        }

    if tool == "add_fillet":
        payload = (tool_payloads or [{}])[0]
        merged = {**ctx, **payload}
        radius = _pf(merged, "radius_mm", "radius", default=1.0)
        raw = merged.get("edge_names", [])
        edge_names = [str(e) for e in raw] if isinstance(raw, list) else []
        _ok(await adapter.add_fillet(radius, edge_names), "add_fillet")
        return {
            "tool": tool,
            "status": "success",
            "message": f"Fillet radius={radius}mm",
        }

    if tool == "check_sketch_fully_defined":
        payload = (tool_payloads or [{}])[0]
        check_sketch_name: str | None = {**ctx, **payload}.get("sketch_name")
        _ok(
            await adapter.check_sketch_fully_defined(
                str(check_sketch_name) if check_sketch_name else None
            ),
            "check_sketch_fully_defined",
        )
        return {
            "tool": tool,
            "status": "success",
            "message": "Checked sketch definition",
        }

    if tool == "save_file":
        payload = (tool_payloads or [{}])[0]
        file_path = str({**ctx, **payload}.get("file_path", ""))
        if not file_path:
            raise ValueError("save_file requires file_path")
        _ok(await adapter.save_file(file_path), "save_file")
        return {"tool": tool, "status": "success", "message": f"Saved '{file_path}'"}

    if tool == "get_model_info":
        _ok(await adapter.get_model_info(), "get_model_info")
        return {"tool": tool, "status": "success", "message": "Retrieved model info"}

    if tool == "list_features":
        _ok(await adapter.list_features(include_suppressed=True), "list_features")
        return {"tool": tool, "status": "success", "message": "Listed features"}

    if tool == "get_mass_properties":
        _ok(await adapter.get_mass_properties(), "get_mass_properties")
        return {
            "tool": tool,
            "status": "success",
            "message": "Retrieved mass properties",
        }

    if tool == "analyze_geometry":
        _ok(await adapter.get_model_info(), "get_model_info")
        _ok(await adapter.list_features(include_suppressed=True), "list_features")
        _ok(await adapter.get_mass_properties(), "get_mass_properties")
        return {
            "tool": tool,
            "status": "success",
            "message": "Geometry analysis completed",
        }

    if tool == "export_image":
        payloads = tool_payloads
        payload = payloads[0] if payloads else ctx.get("export_image") or {}
        if not isinstance(payload, dict):
            raise ValueError("export_image must be an object payload")
        _ok(await adapter.export_image(payload), "export_image")
        return {"tool": tool, "status": "success", "message": "Exported image"}

    return None  # Unknown tool → caller mocks it


async def _run_checkpoint_tools(
    planned: dict[str, Any],
    *,
    session_id: str = DEFAULT_SESSION_ID,
    checkpoint_index: int = 0,
    checkpoint_title: str = "",
    repair_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute checkpoint tools directly via the adapter with mocked-tool handling.

    Generates the checkpoint script as an audit artifact but executes tools
    in-process so that test adapters (monkeypatched create_adapter) work.
    Tools in _MOCKED_TOOLS and unrecognized tool names are recorded as mocked
    and do not block checkpoint success.
    """
    tools = _planned_tools(planned)
    script_dir = _checkpoint_script_dir(session_id)
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = _checkpoint_script_path(session_id, checkpoint_index)
    script_text = _render_checkpoint_script(
        planned,
        session_id=session_id,
        checkpoint_index=checkpoint_index,
        checkpoint_title=checkpoint_title,
    )
    script_path.write_text(script_text, encoding="utf-8")

    tool_runs: list[dict[str, Any]] = []
    failed_tools: list[str] = []
    mocked_tools: list[str] = []

    config = load_config()
    adapter = await create_adapter(config)
    try:
        await adapter.connect()
    except Exception as adapter_error:
        return {
            "tool_runs": [
                {
                    "tool": "checkpoint.execute",
                    "status": "error",
                    "message": f"Adapter connection failed: {adapter_error}",
                }
            ],
            "failed_tools": ["checkpoint.execute"],
            "mocked_tools": [],
            "script_path": str(script_path),
            "script_text": script_text,
            "stdout_text": "",
            "stderr_text": str(adapter_error),
            "validation_failures": [],
        }

    try:
        for tool in tools:
            if tool in _MOCKED_TOOLS:
                mocked_tools.append(tool)
                tool_runs.append(
                    {
                        "tool": tool,
                        "status": "mocked",
                        "message": f"{tool} — mocked (no adapter binding in this build)",
                    }
                )
                continue

            try:
                run = await _execute_tool(adapter, planned, tool)
            except Exception as exc:
                failed_tools.append(tool)
                tool_runs.append({"tool": tool, "status": "error", "message": str(exc)})
                break

            if run is None:
                mocked_tools.append(tool)
                tool_runs.append(
                    {
                        "tool": tool,
                        "status": "mocked",
                        "message": f"Unknown tool '{tool}' — mocked",
                    }
                )
            else:
                tool_runs.append(run)
    finally:
        try:
            await adapter.disconnect()
        except Exception:
            pass

    return {
        "tool_runs": tool_runs,
        "failed_tools": failed_tools,
        "mocked_tools": mocked_tools,
        "script_path": str(script_path),
        "script_text": script_text,
        "stdout_text": "",
        "stderr_text": "",
        "validation_failures": [],
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
    from .session_service import (  # noqa: PLC0415
        build_dashboard_state,
        ensure_dashboard_session,
    )

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
    session_meta = parse_json_blob(session_row.get("metadata_json"))

    if _should_open_empty_part(session_meta, planned):
        await _open_empty_part_before_checkpoint(
            session_id=session_id,
            session_row=session_row,
            db_path=db_path,
            api_origin=DEFAULT_API_ORIGIN,
        )

    run_summary = await _run_checkpoint_tools(
        planned,
        session_id=session_id,
        checkpoint_index=int(target["checkpoint_index"]),
        checkpoint_title=str(target["title"]),
        repair_context={
            "active_sketch_plane": session_meta.get("active_sketch_plane"),
            "last_sketch_name": session_meta.get("last_sketch_name"),
            "user_goal": session_row.get("user_goal") or DEFAULT_USER_GOAL,
        },
    )
    failed_tools = run_summary["failed_tools"]
    tool_runs = run_summary["tool_runs"]
    mocked_tools = run_summary.get("mocked_tools", [])
    executed = not failed_tools

    if failed_tools:
        message = (
            f"Checkpoint {target['checkpoint_index']} failed on tools: "
            f"{', '.join(failed_tools)}."
        )
    elif mocked_tools and not any(r.get("status") == "success" for r in tool_runs):
        message = (
            f"Checkpoint {target['checkpoint_index']} executed "
            f"(tools MOCKED: {', '.join(mocked_tools)})."
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
            "failed_tools": failed_tools,
            "script_path": run_summary.get("script_path", ""),
            "script_text": run_summary.get("script_text", ""),
            "stdout_tail": str(run_summary.get("stdout_text", ""))[-4000:],
            "stderr_tail": str(run_summary.get("stderr_text", ""))[-4000:],
            "validation_failures": run_summary.get("validation_failures", []),
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
        latest_error_text=(message if failed_tools else ""),
        remediation_hint=(
            "Open the generated checkpoint script, repair planned parameters, then rerun this checkpoint."
            if failed_tools
            else ""
        ),
    )
    return build_dashboard_state(session_id, db_path=db_path)
