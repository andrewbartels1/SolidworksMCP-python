"""Preview and feature-highlighting service for the Prefab CAD assistant dashboard.

Exports PNG screenshots and 3D geometry (GLB/STL) from the active SolidWorks model and
persists preview state in the session.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from ...adapters import create_adapter
from ...config import load_config
from ...agents.history_db import (
    insert_model_state_snapshot,
    insert_tool_call_record,
    list_model_state_snapshots,
    get_design_session,
)
from ._utils import (
    DEFAULT_API_ORIGIN,
    DEFAULT_PREVIEW_ORIENTATION,
    ensure_preview_dir,
    merge_metadata,
    parse_json_blob,
    sanitize_preview_viewer_url,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _public_preview_url(
    preview_path: Path,
    *,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> str:
    """Build a cache-busting public URL for a preview image.

    Args:
        preview_path: Filesystem path to the preview image.
        api_origin: Base URL of the running FastAPI server.

    Returns:
        Public URL string with a ``ts`` query parameter.
    """
    timestamp = (
        int(preview_path.stat().st_mtime) if preview_path.exists() else int(time.time())
    )
    return f"{api_origin}/previews/{preview_path.name}?ts={timestamp}"


async def _reopen_target_model_for_preview(adapter: Any, model_path: str, *, context: str) -> None:
    """Reopen the persisted target model before preview export."""
    candidate_path = Path(str(model_path))
    if not candidate_path.exists():
        raise RuntimeError(f"Target model path for {context} does not exist: {candidate_path}")

    logger.info(
        "[ui.refresh_preview] reopening target model for {} {}",
        context,
        str(candidate_path.resolve()),
    )
    reopen_result = await adapter.open_model(str(candidate_path.resolve()))
    if not getattr(reopen_result, "is_success", False):
        raise RuntimeError(
            reopen_result.error
            or f"Failed to reopen target model for {context}: {candidate_path.resolve()}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def refresh_preview(
    session_id: str,
    *,
    orientation: str = DEFAULT_PREVIEW_ORIENTATION,
    db_path: Path | None = None,
    preview_dir: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
    adapter_override: Any | None = None,
    active_model_path_override: str | None = None,
    reopen_active_model: bool = True,
) -> dict[str, Any]:
    """Export the current SolidWorks viewport to a PNG preview and GLB/STL for the 3D viewer.

    Args:
        session_id: Dashboard session identifier.
        orientation: View orientation for the PNG export
            (``"front"``, ``"top"``, ``"right"``, ``"isometric"``, ``"current"``).
        db_path: Optional SQLite path override.
        preview_dir: Override for the preview output directory.
        api_origin: Base URL of the running FastAPI server.
        adapter_override: Pre-connected adapter (avoids creating a second connection when
            called from ``connect_target_model``).
        active_model_path_override: Override for the model path to reopen.
        reopen_active_model: When ``True``, reopen the persisted active model path before
            exporting (default).

    Returns:
        Full dashboard state payload.
    """
    from .session_service import build_dashboard_state, ensure_dashboard_session  # noqa: PLC0415

    ensure_dashboard_session(session_id, db_path=db_path)
    logger.info(
        "[ui.refresh_preview] session_id={} orientation={}",
        session_id,
        orientation,
    )
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = parse_json_blob(session_row.get("metadata_json"))
    preview_viewer_url = sanitize_preview_viewer_url(
        metadata.get("preview_viewer_url"),
        session_id=session_id,
        api_origin=api_origin,
    )
    resolved_preview_dir = ensure_preview_dir(preview_dir)
    preview_path = resolved_preview_dir / f"{session_id}.png"
    active_model_path = active_model_path_override or metadata.get("active_model_path")
    adapter = adapter_override
    owns_adapter = adapter_override is None

    try:
        if not active_model_path:
            raise RuntimeError(
                "No attached model path found for preview refresh. Attach a target model first."
            )

        if adapter is None:
            config = load_config()
            adapter = await create_adapter(config)
        if owns_adapter:
            await adapter.connect()
        if reopen_active_model and hasattr(adapter, "open_model"):
            await _reopen_target_model_for_preview(
                adapter, str(active_model_path), context="preview"
            )

        # --- Step 1: Export 3D geometry for the Three.js viewer (GLB preferred) ---
        glb_path = resolved_preview_dir / f"{session_id}.glb"
        stl_path = resolved_preview_dir / f"{session_id}.stl"
        viewer_ts = int(time.time())
        viewer_format = "none"
        try:
            glb_result = await adapter.export_file(str(glb_path.resolve()), "glb")
            if (
                glb_result.is_success
                and glb_path.exists()
                and glb_path.stat().st_size > 0
            ):
                viewer_format = "glb"
                viewer_ts = int(glb_path.stat().st_mtime)
                logger.info(
                    "[ui.refresh_preview] GLB export succeeded path={}",
                    str(glb_path.resolve()),
                )
        except Exception as _glb_exc:
            logger.warning("[ui.refresh_preview] GLB export failed: {}", str(_glb_exc))

        if viewer_format == "none":
            try:
                stl_result = await adapter.export_file(str(stl_path.resolve()), "stl")
                if (
                    stl_result.is_success
                    and stl_path.exists()
                    and stl_path.stat().st_size > 0
                ):
                    viewer_format = "stl"
                    viewer_ts = int(stl_path.stat().st_mtime)
                    logger.info(
                        "[ui.refresh_preview] STL export succeeded path={}",
                        str(stl_path.resolve()),
                    )
            except Exception:
                logger.debug("[ui.refresh_preview] STL export skipped (adapter error)")

        preview_viewer_url = (
            f"{api_origin}/api/ui/viewer/{session_id}?t={viewer_ts}&fmt={viewer_format}"
        )

        # --- Step 2: Export PNG screenshot (best-effort) ---
        png_payload = {
            "file_path": str(preview_path.resolve()),
            "format_type": "png",
            "width": 1280,
            "height": 720,
            "view_orientation": orientation,
        }
        png_ok = False
        png_error: str = ""
        snapshot_id: int | None = None
        try:
            result = await adapter.export_image(png_payload)
            if result.is_success and preview_path.exists():
                png_ok = True
                logger.info(
                    "[ui.refresh_preview] PNG export succeeded file_path={}",
                    str(preview_path.resolve()),
                )
                snapshot_id = insert_model_state_snapshot(
                    session_id=session_id,
                    screenshot_path=str(preview_path.resolve()),
                    state_fingerprint=f"preview-{preview_path.stat().st_mtime_ns}",
                    db_path=db_path,
                )
                insert_tool_call_record(
                    session_id=session_id,
                    tool_name="export_image",
                    input_json=json.dumps(png_payload, ensure_ascii=True),
                    output_json=json.dumps(result.data or {}, ensure_ascii=True),
                    success=True,
                    db_path=db_path,
                )
            else:
                png_error = result.error or "export_image returned failure"
                logger.warning("[ui.refresh_preview] PNG export failed: {}", png_error)
        except Exception as png_exc:
            png_error = str(png_exc)
            logger.warning("[ui.refresh_preview] PNG export exception: {}", png_exc)

        if owns_adapter:
            await adapter.disconnect()

        # --- Step 3: Export per-orientation PNG thumbnails ---
        VIEW_ORIENTATIONS = ["isometric", "front", "top", "right"]
        preview_view_urls: dict[str, str] = {}
        try:
            config2 = load_config()
            adapter2 = await create_adapter(config2)
            await adapter2.connect()
            if hasattr(adapter2, "open_model"):
                await _reopen_target_model_for_preview(
                    adapter2,
                    str(active_model_path),
                    context="orientation previews",
                )
            _sel_name = str(
                metadata.get("selected_feature_selector_name")
                or metadata.get("selected_feature_name")
                or ""
            ).strip()
            if _sel_name and hasattr(adapter2, "select_feature"):
                try:
                    await adapter2.select_feature(_sel_name)
                    logger.info(
                        "[ui.refresh_preview] re-selected '{}' before view screenshots",
                        _sel_name,
                    )
                except Exception as _sel_exc:
                    logger.debug(
                        "[ui.refresh_preview] re-select '{}' failed (non-fatal): {}",
                        _sel_name,
                        _sel_exc,
                    )
            for view_name in VIEW_ORIENTATIONS:
                view_path = resolved_preview_dir / f"{session_id}-{view_name}.png"
                try:
                    if _sel_name and hasattr(adapter2, "select_feature"):
                        await adapter2.select_feature(_sel_name)
                    view_result = await adapter2.export_image(
                        {
                            "file_path": str(view_path.resolve()),
                            "format_type": "png",
                            "width": 640,
                            "height": 480,
                            "view_orientation": view_name,
                        }
                    )
                    if view_result.is_success and view_path.exists():
                        ts = int(view_path.stat().st_mtime)
                        preview_view_urls[view_name] = (
                            f"{api_origin}/previews/{view_path.name}?ts={ts}"
                        )
                        logger.info(
                            "[ui.refresh_preview] view PNG {} exported", view_name
                        )
                    else:
                        logger.warning(
                            "[ui.refresh_preview] view PNG {} failed: {}",
                            view_name,
                            view_result.error or "no detail",
                        )
                except Exception as _ve:
                    logger.warning(
                        "[ui.refresh_preview] view PNG {} exception: {}",
                        view_name,
                        str(_ve),
                    )
            await adapter2.disconnect()
        except Exception as _views_exc:
            logger.warning(
                "[ui.refresh_preview] multi-view export failed: {}", str(_views_exc)
            )

        # Preserve existing view URLs when a refresh attempt returns no images.
        existing_view_urls = metadata.get("preview_view_urls")
        if isinstance(existing_view_urls, dict):
            if not preview_view_urls:
                preview_view_urls = dict(existing_view_urls)
            else:
                merged_view_urls = dict(existing_view_urls)
                merged_view_urls.update(preview_view_urls)
                preview_view_urls = merged_view_urls

        viewer_label = (
            f"3D viewer ({viewer_format.upper()})"
            if viewer_format != "none"
            else "3D viewer (no model)"
        )
        png_label = "PNG" if png_ok else f"no PNG ({png_error})"
        status_msg = f"Preview refreshed ({viewer_label}, {png_label})."

        merge_metadata(
            session_id,
            db_path=db_path,
            preview_orientation=orientation,
            latest_message=status_msg,
            preview_status=status_msg,
            latest_snapshot_id=(str(snapshot_id) if snapshot_id is not None else ""),
            preview_viewer_url=preview_viewer_url,
            preview_stl_ready=(viewer_format != "none"),
            preview_png_ready=png_ok,
            preview_view_urls=preview_view_urls,
            latest_error_text="",
            remediation_hint="",
        )
    except Exception as exc:
        logger.exception("[ui.refresh_preview] failed: {}", exc)
        insert_tool_call_record(
            session_id=session_id,
            tool_name="export_image",
            input_json=json.dumps({"orientation": orientation}, ensure_ascii=True),
            output_json=json.dumps({"error": str(exc)}, ensure_ascii=True),
            success=False,
            db_path=db_path,
        )
        merge_metadata(
            session_id,
            db_path=db_path,
            latest_message=f"Preview refresh failed: {exc}",
            preview_status=f"Preview refresh failed: {exc}",
            preview_orientation=orientation,
            latest_error_text=str(exc),
            remediation_hint="Open a model in SolidWorks and retry preview refresh.",
        )

    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


async def highlight_feature(
    session_id: str,
    feature_name: str,
    *,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Select and highlight a named feature in the active SolidWorks model.

    Args:
        session_id: Dashboard session identifier.
        feature_name: Name of the feature to select (must match the feature-tree entry).
        db_path: Optional SQLite path override.
        api_origin: Base URL of the running FastAPI server.

    Returns:
        Full dashboard state payload.
    """
    from .session_service import build_dashboard_state, ensure_dashboard_session  # noqa: PLC0415

    ensure_dashboard_session(session_id, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = parse_json_blob(session_row.get("metadata_json"))
    active_model_path = metadata.get("active_model_path")
    resolved_name = (feature_name or "").strip()
    if not resolved_name:
        merge_metadata(
            session_id,
            db_path=db_path,
            latest_error_text="No feature name provided for selection.",
            remediation_hint="Pass a non-empty feature_name.",
        )
        return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)

    try:
        known_feature_names: set[str] = set()
        for snapshot in list_model_state_snapshots(session_id, db_path=db_path):
            raw_tree = snapshot.get("feature_tree_json")
            if not raw_tree:
                continue
            try:
                parsed_tree = json.loads(raw_tree)
            except Exception:
                continue
            if isinstance(parsed_tree, list):
                known_feature_names.update(
                    str(item.get("name") or "").strip()
                    for item in parsed_tree
                    if str(item.get("name") or "").strip()
                )
                if known_feature_names:
                    break

        config = load_config()
        adapter = await create_adapter(config)
        await adapter.connect()
        if active_model_path and hasattr(adapter, "open_model"):
            candidate = Path(str(active_model_path))
            if candidate.exists():
                await adapter.open_model(str(candidate.resolve()))
        selected = False
        entity_type = ""
        selected_name = resolved_name
        if hasattr(adapter, "select_feature"):
            result = await adapter.select_feature(resolved_name)
            if result.is_success and isinstance(result.data, dict):
                selected = bool(result.data.get("selected"))
                entity_type = str(result.data.get("entity_type") or "")
                selected_name = str(result.data.get("selected_name") or resolved_name)
        await adapter.disconnect()
        tracked_only = (not selected) and (resolved_name in known_feature_names)
        merge_metadata(
            session_id,
            db_path=db_path,
            selected_feature_name=resolved_name,
            selected_feature_selector_name=selected_name,
            latest_message=(
                f"Selected '{resolved_name}' ({entity_type}) in SolidWorks."
                if selected
                else (
                    f"Tracking '{resolved_name}' from the feature tree. "
                    "SolidWorks did not expose a direct selectable handle for that row."
                    if tracked_only
                    else f"Could not select feature '{resolved_name}' — name may not match the feature tree."
                )
            ),
            latest_error_text=(
                ""
                if (selected or tracked_only)
                else f"SelectByID2 returned False for '{resolved_name}'."
            ),
            remediation_hint=(
                ""
                if (selected or tracked_only)
                else "Check that the feature name exactly matches the SolidWorks feature tree entry."
            ),
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.highlight_feature",
            input_json=json.dumps({"feature_name": resolved_name}, ensure_ascii=True),
            output_json=json.dumps(
                {
                    "selected": selected,
                    "tracked_only": tracked_only,
                    "entity_type": entity_type,
                },
                ensure_ascii=True,
            ),
            success=(selected or tracked_only),
            db_path=db_path,
        )
    except Exception as exc:
        logger.exception("[ui.highlight_feature] failed: {}", exc)
        merge_metadata(
            session_id,
            db_path=db_path,
            latest_error_text=str(exc),
            remediation_hint="Ensure SolidWorks is open with the target model loaded.",
        )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)
