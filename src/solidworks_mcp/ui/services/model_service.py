"""Model connection and upload service for the Prefab CAD assistant dashboard.

Handles opening a target SolidWorks model (open-only) and connecting to it
(open + inspect feature tree + trigger preview refresh).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from ...adapters import create_adapter
from ...agents.history_db import (
    insert_evidence_link,
    insert_model_state_snapshot,
    insert_tool_call_record,
)
from ...config import load_config
from ...utils.feature_tree_classifier import classify_feature_tree_snapshot
from ._utils import (
    DEFAULT_API_ORIGIN,
    DEFAULT_PREVIEW_ORIENTATION,
    ensure_preview_dir,
    materialize_uploaded_model,
    merge_metadata,
    sanitize_model_path_text,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def open_target_model(
    session_id: str,
    *,
    model_path: str | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    feature_target_text: str | None = None,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Open a target model in SolidWorks and persist session state.

    Args:
        session_id: Dashboard session identifier.
        model_path: Absolute path to the SolidWorks model file.
        uploaded_files: List of base64-encoded file upload dicts.
        feature_target_text: Optional comma-separated feature target references.
        db_path: Optional SQLite path override.
        api_origin: Base URL of the running FastAPI server.

    Returns:
        Full dashboard state payload.
    """
    from .session_service import (  # noqa: PLC0415
        build_dashboard_state,
        ensure_dashboard_session,
    )

    ensure_dashboard_session(session_id, db_path=db_path)
    adapter = None
    resolved_path: Path | None = None

    logger.info(
        "[ui.open_target_model] session_id={} model_path={} uploaded_files={} feature_targets={}",
        session_id,
        model_path,
        len(uploaded_files) if uploaded_files else 0,
        feature_target_text or "",
    )

    resolved_path = _resolve_model_path(
        session_id,
        model_path=model_path,
        uploaded_files=uploaded_files,
        feature_target_text=feature_target_text,
        db_path=db_path,
        api_origin=api_origin,
    )
    if resolved_path is None:
        return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)

    config = load_config()
    adapter = await create_adapter(config)
    model_info: dict[str, Any] = {}
    tool_input = {
        "model_path": str(resolved_path.resolve()),
        "uploaded_file_name": uploaded_files[0].get("name") if uploaded_files else None,
        "feature_target_text": feature_target_text or "",
    }
    try:
        await adapter.connect()
        open_result = await adapter.open_model(str(resolved_path.resolve()))
        if not open_result.is_success:
            raise RuntimeError(open_result.error or "Failed to open target model.")

        if hasattr(adapter, "get_model_info"):
            info_result = await adapter.get_model_info()
            if info_result.is_success and isinstance(info_result.data, dict):
                model_info = info_result.data

        metadata = merge_metadata(
            session_id,
            db_path=db_path,
            workflow_mode="edit_existing",
            active_model_path=str(resolved_path.resolve()),
            active_model_status=(
                f"Opened model: {resolved_path.name}"
                f" | type={model_info.get('type', 'unknown')}"
            ),
            active_model_type=str(model_info.get("type") or ""),
            active_model_configuration=str(
                model_info.get("configuration") or "Default"
            ),
            feature_target_text=feature_target_text or "",
            latest_message=f"Opened target model {resolved_path.name} in SolidWorks.",
            latest_error_text="",
            remediation_hint="",
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.open_target_model",
            input_json=json.dumps(tool_input, ensure_ascii=True),
            output_json=json.dumps(metadata, ensure_ascii=True),
            success=True,
            db_path=db_path,
        )
    except Exception as exc:
        logger.exception(
            "[ui.open_target_model] failed session_id={} path={} error={}",
            session_id,
            str(resolved_path.resolve()) if resolved_path else "<none>",
            exc,
        )
        merge_metadata(
            session_id,
            db_path=db_path,
            workflow_mode="edit_existing",
            active_model_path=str(resolved_path.resolve()),
            feature_target_text=feature_target_text or "",
            latest_message="Failed to open target model.",
            latest_error_text=str(exc),
            remediation_hint="Open SolidWorks, verify COM access, and retry with a valid .sldprt/.sldasm path.",
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.open_target_model",
            input_json=json.dumps(tool_input, ensure_ascii=True),
            output_json=json.dumps({"error": str(exc)}, ensure_ascii=True),
            success=False,
            db_path=db_path,
        )
    finally:
        if adapter is not None:
            try:
                await adapter.disconnect()
            except Exception:
                logger.debug("Adapter disconnect failed during open-model cleanup")

    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


async def connect_target_model(
    session_id: str,
    *,
    model_path: str | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    feature_target_text: str | None = None,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Open a target model, inspect its feature tree, and trigger a preview refresh.

    Args:
        session_id: Dashboard session identifier.
        model_path: Absolute path to the SolidWorks model file.
        uploaded_files: List of base64-encoded file upload dicts.
        feature_target_text: Optional comma-separated feature target references.
        db_path: Optional SQLite path override.
        api_origin: Base URL of the running FastAPI server.

    Returns:
        Full dashboard state payload (includes preview state after the refresh).
    """
    from .preview_service import refresh_preview  # noqa: PLC0415
    from .session_service import (  # noqa: PLC0415
        build_dashboard_state,
        ensure_dashboard_session,
    )

    ensure_dashboard_session(session_id, db_path=db_path)
    adapter = None
    resolved_path: Path | None = None

    logger.info(
        "[ui.connect_target_model] session_id={} model_path={} uploaded_files={} feature_targets={}",
        session_id,
        model_path,
        len(uploaded_files) if uploaded_files else 0,
        feature_target_text or "",
    )

    resolved_path = _resolve_model_path(
        session_id,
        model_path=model_path,
        uploaded_files=uploaded_files,
        feature_target_text=feature_target_text,
        db_path=db_path,
        api_origin=api_origin,
    )
    if resolved_path is None:
        return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)

    config = load_config()
    adapter = await create_adapter(config)
    model_info: dict[str, Any] = {}
    features: list[dict[str, Any]] = []
    attach_succeeded = False
    tool_input = {
        "model_path": str(resolved_path.resolve()),
        "uploaded_file_name": uploaded_files[0].get("name") if uploaded_files else None,
        "feature_target_text": feature_target_text or "",
    }
    try:
        await adapter.connect()
        open_result = await adapter.open_model(str(resolved_path.resolve()))
        if not open_result.is_success:
            raise RuntimeError(open_result.error or "Failed to open target model.")

        if hasattr(adapter, "get_model_info"):
            info_result = await adapter.get_model_info()
            if info_result.is_success and isinstance(info_result.data, dict):
                model_info = info_result.data

        if hasattr(adapter, "list_features"):
            feature_result = await adapter.list_features(include_suppressed=True)
            if feature_result.is_success and isinstance(feature_result.data, list):
                features = [
                    item for item in feature_result.data if isinstance(item, dict)
                ]

        from ._utils import feature_target_status  # noqa: PLC0415

        classification = classify_feature_tree_snapshot(model_info, features)  # type: ignore[arg-type]
        target_status, matched_targets, missing_targets = feature_target_status(
            features, feature_target_text
        )

        snapshot_id = insert_model_state_snapshot(
            session_id=session_id,
            model_path=str(resolved_path.resolve()),
            feature_tree_json=json.dumps(features, ensure_ascii=True),
            state_fingerprint=f"{resolved_path.resolve()}::{resolved_path.stat().st_mtime_ns}",
            db_path=db_path,
        )
        for evidence_line in classification.get("evidence", []):
            insert_evidence_link(
                session_id=session_id,
                source_type="active_model",
                source_id=str(resolved_path.resolve()),
                relevance_score=0.96,
                rationale=str(evidence_line),
                payload_json=json.dumps(classification, ensure_ascii=True),
                db_path=db_path,
            )

        if matched_targets or missing_targets:
            insert_evidence_link(
                session_id=session_id,
                source_type="feature_target",
                source_id=str(resolved_path.resolve()),
                relevance_score=0.9 if matched_targets else 0.4,
                rationale=target_status,
                payload_json=json.dumps(
                    {"matched": matched_targets, "missing": missing_targets},
                    ensure_ascii=True,
                ),
                db_path=db_path,
            )

        metadata = merge_metadata(
            session_id,
            db_path=db_path,
            workflow_mode="edit_existing",
            active_model_path=str(resolved_path.resolve()),
            active_model_status=(
                f"Attached model: {resolved_path.name}"
                f" | type={model_info.get('type', 'unknown')}"
                f" | features={len(features)}"
            ),
            active_model_type=str(model_info.get("type") or ""),
            active_model_configuration=str(
                model_info.get("configuration") or "Default"
            ),
            feature_target_text=feature_target_text or "",
            feature_target_status=target_status,
            proposed_family=classification.get("family") or "unknown",
            family_confidence=classification.get("confidence") or "low",
            family_evidence=classification.get("evidence") or [],
            family_warnings=classification.get("warnings") or [],
            latest_message=(
                f"Opened target model {resolved_path.name}. Generating preview views..."
            ),
            preview_status="Generating preview views from attached model...",
            preview_stl_ready=False,
            preview_png_ready=False,
            preview_viewer_url="",
            latest_error_text="",
            remediation_hint="",
            latest_snapshot_id=snapshot_id,
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.connect_target_model",
            input_json=json.dumps(tool_input, ensure_ascii=True),
            output_json=json.dumps(metadata, ensure_ascii=True),
            success=True,
            db_path=db_path,
        )
        attach_succeeded = True
    except Exception as exc:
        logger.exception(
            "[ui.connect_target_model] failed session_id={} path={} error={}",
            session_id,
            str(resolved_path.resolve()) if resolved_path else "<none>",
            exc,
        )
        merge_metadata(
            session_id,
            db_path=db_path,
            workflow_mode="edit_existing",
            active_model_path=str(resolved_path.resolve()),
            feature_target_text=feature_target_text or "",
            latest_message="Failed to attach target model.",
            preview_status="Preview generation failed while attaching model.",
            latest_error_text=str(exc),
            remediation_hint="Open SolidWorks, verify COM access, and retry with a valid .sldprt/.sldasm path.",
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.connect_target_model",
            input_json=json.dumps(tool_input, ensure_ascii=True),
            output_json=json.dumps({"error": str(exc)}, ensure_ascii=True),
            success=False,
            db_path=db_path,
        )

    if attach_succeeded:
        try:
            return await refresh_preview(
                session_id,
                orientation=DEFAULT_PREVIEW_ORIENTATION,
                db_path=db_path,
                preview_dir=ensure_preview_dir(),
                api_origin=api_origin,
                adapter_override=adapter,
                active_model_path_override=str(resolved_path.resolve()),
                reopen_active_model=False,
            )
        except Exception as refresh_exc:
            logger.warning(
                "[ui.connect_target_model] post-attach preview refresh failed: {}",
                str(refresh_exc),
            )

    if adapter is not None:
        try:
            await adapter.disconnect()
        except Exception:
            logger.debug("Adapter disconnect failed during target-model cleanup")

    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_model_path(
    session_id: str,
    *,
    model_path: str | None,
    uploaded_files: list[dict[str, Any]] | None,
    feature_target_text: str | None,
    db_path: Path | None,
    api_origin: str,
) -> Path | None:
    """Resolve and validate the model path from either upload payload or explicit path.

    Args:
        session_id: Dashboard session identifier.
        model_path: Explicit absolute path string.
        uploaded_files: Optional list of upload dicts.
        feature_target_text: Optional feature target annotation.
        db_path: Optional SQLite path override.
        api_origin: Base URL of the running FastAPI server.

    Returns:
        Resolved ``Path`` on success, ``None`` when validation fails (error state
        already persisted to the session).
    """
    if uploaded_files:
        try:
            return materialize_uploaded_model(session_id, uploaded_files)
        except RuntimeError as exc:
            merge_metadata(
                session_id,
                db_path=db_path,
                latest_message="Uploaded model could not be prepared.",
                latest_error_text=str(exc),
                remediation_hint="Choose a valid .sldprt or .sldasm file and retry.",
                feature_target_text=feature_target_text or "",
                workflow_mode="edit_existing",
            )
            return None

    if model_path:
        normalized = sanitize_model_path_text(model_path)
        if not normalized:
            merge_metadata(
                session_id,
                db_path=db_path,
                latest_message="No target model was provided.",
                latest_error_text="Missing model path or uploaded model file.",
                remediation_hint="Choose a local SolidWorks file or provide an absolute model path.",
                feature_target_text=feature_target_text or "",
                workflow_mode="edit_existing",
            )
            return None
        resolved = Path(normalized).expanduser()
        if not resolved.exists():
            merge_metadata(
                session_id,
                db_path=db_path,
                latest_message="Target model path was not found.",
                latest_error_text=f"Missing file: {resolved}",
                remediation_hint="Provide an absolute path to an existing .sldprt or .sldasm file.",
                active_model_path=str(resolved),
                feature_target_text=feature_target_text or "",
                workflow_mode="edit_existing",
            )
            return None
        return resolved

    merge_metadata(
        session_id,
        db_path=db_path,
        latest_message="No target model was provided.",
        latest_error_text="Missing model path or uploaded model file.",
        remediation_hint="Choose a local SolidWorks file or provide an absolute model path.",
        feature_target_text=feature_target_text or "",
        workflow_mode="edit_existing",
    )
    return None
