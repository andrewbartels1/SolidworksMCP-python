"""Compatibility shim for legacy imports from solidworks_mcp.ui.service.

The UI backend was split into focused modules under solidworks_mcp.ui.services.
This module preserves historical import paths used by tests and external callers.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..adapters import create_adapter
from ..agents.history_db import (
    get_design_session,
    insert_model_state_snapshot,
    list_plan_checkpoints,
    upsert_design_session,
)
from ..agents.retrieval_index import _chunk_text
from ..agents.schemas import RecoverableFailure as _AgentRecoverableFailure
from ..config import load_config
from .services import *  # noqa: F401,F403,F405
from .services import _utils as _utils_service
from .services import checkpoint_service as _checkpoint_service
from .services import docs_service as _docs_service
from .services import llm_service as _llm_service
from .services import model_service as _model_service
from .services import preview_service as _preview_service
from .services import session_service as _session_service
from .services._utils import DEFAULT_API_ORIGIN, DEFAULT_PREVIEW_ORIENTATION
from .services._utils import (
    context_file_path as _context_file_path_impl,
)
from .services._utils import (
    materialize_uploaded_model as _materialize_uploaded_model_impl,
)
from .services._utils import (
    merge_metadata as _merge_metadata,
)
from .services._utils import (
    normalize_feature_targets as _normalize_feature_targets,
)
from .services._utils import (
    safe_context_name as _safe_context_name,
)
from .services._utils import (
    sanitize_model_path_text as _sanitize_model_path_text,
)
from .services._utils import (
    sanitize_preview_viewer_url as _sanitize_preview_viewer_url,
)
from .services.llm_service import (
    Agent,
    OpenAIChatModel,
    OpenAIProvider,
    _ensure_provider_credentials,
)

_ORIG_BUILD_AGENT_MODEL = _llm_service._build_agent_model
_ORIG_RUN_STRUCTURED_AGENT = _llm_service._run_structured_agent

# Keep compatibility with tests importing this symbol from agents.schemas.
RecoverableFailure = _AgentRecoverableFailure

# Legacy constants expected by helper tests.
DEFAULT_CONTEXT_DIR = _utils_service._DEFAULT_CONTEXT_DIR
DEFAULT_UPLOADED_MODEL_DIR = _utils_service._DEFAULT_UPLOADED_MODEL_DIR

# Keep this symbol available for tests that monkeypatch PDF ingestion behavior.
try:  # pragma: no cover
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None


# Legacy helper retained for test compatibility.
def _default_model_for_profile(provider: str, profile: str) -> str:
    if provider == "local":
        profile_models = {
            "small": "local:gemma4:e2b",
            "balanced": "local:gemma4:e4b",
            "large": "local:gemma4:26b",
        }
        return profile_models.get(
            (profile or "balanced").lower(), profile_models["balanced"]
        )

    profile_models = {
        "small": "github:openai/gpt-4.1-mini",
        "balanced": "github:openai/gpt-4.1",
        "large": "github:openai/gpt-4.1",
    }
    return profile_models.get(
        (profile or "balanced").lower(), profile_models["balanced"]
    )


@contextmanager
def _temporary_module_bindings(module: Any, **bindings: Any):
    original: dict[str, Any] = {}
    for name, value in bindings.items():
        if hasattr(module, name):
            original[name] = getattr(module, name)
        setattr(module, name, value)
    try:
        yield
    finally:
        for name in bindings:
            if name in original:
                setattr(module, name, original[name])


def _read_reference_source(source_path: Path) -> str:
    return _utils_service.read_reference_source(source_path)


def _read_reference_url(source_url: str) -> tuple[str, str]:
    request = Request(source_url, headers={"User-Agent": "SolidWorksMCP/1.0"})
    with urlopen(request, timeout=20) as response:
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
        raw_bytes = response.read()

    parsed = urlparse(source_url)
    label = Path(parsed.path).name or parsed.netloc or source_url
    suffix = Path(parsed.path).suffix.lower()

    if content_type == "application/pdf" or suffix == ".pdf":
        if PdfReader is None:
            raise RuntimeError(
                "Install pypdf to ingest PDF sources, or provide a text, markdown, or HTML source instead."
            )
        reader = PdfReader(BytesIO(raw_bytes))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
        return text, label

    decoded = raw_bytes.decode(charset, errors="ignore")
    if "html" in content_type or suffix in {".html", ".htm"}:
        parser = _utils_service.HTMLTextExtractor()
        parser.feed(decoded)
        return parser.text().strip(), label

    return decoded.strip(), label


def _build_agent_model(model_name: str, local_endpoint: str | None = None):
    with _temporary_module_bindings(
        _llm_service,
        OpenAIProvider=OpenAIProvider,
        OpenAIChatModel=OpenAIChatModel,
    ):
        return _ORIG_BUILD_AGENT_MODEL(model_name, local_endpoint)


async def _run_structured_agent(*args: Any, **kwargs: Any):
    with _temporary_module_bindings(
        _llm_service,
        Agent=Agent,
        RecoverableFailure=RecoverableFailure,
        _ensure_provider_credentials=_ensure_provider_credentials,
        _build_agent_model=_build_agent_model,
    ):
        result = await _ORIG_RUN_STRUCTURED_AGENT(*args, **kwargs)
        if isinstance(result, RecoverableFailure):
            return result
        if all(
            hasattr(result, name)
            for name in (
                "explanation",
                "remediation_steps",
                "retry_focus",
                "should_retry",
            )
        ):
            return RecoverableFailure(
                explanation=str(getattr(result, "explanation", "")),
                remediation_steps=list(getattr(result, "remediation_steps", []) or []),
                retry_focus=str(getattr(result, "retry_focus", "")) or None,
                should_retry=bool(getattr(result, "should_retry", False)),
            )
        return result


def ensure_uploaded_model_dir(upload_dir: Path | None = None) -> Path:
    return _utils_service.ensure_uploaded_model_dir(
        upload_dir or DEFAULT_UPLOADED_MODEL_DIR
    )


def ensure_context_dir(context_dir: Path | None = None) -> Path:
    return _utils_service.ensure_context_dir(context_dir or DEFAULT_CONTEXT_DIR)


def _materialize_uploaded_model(
    session_id: str,
    uploaded_files: list[dict[str, Any]] | None,
    *,
    upload_dir: Path | None = None,
) -> Path:
    return _materialize_uploaded_model_impl(
        session_id,
        uploaded_files,
        upload_dir=upload_dir or DEFAULT_UPLOADED_MODEL_DIR,
    )


def _context_file_path(
    session_id: str,
    *,
    context_name: str | None = None,
    context_dir: Path | None = None,
) -> Path:
    return _context_file_path_impl(
        session_id,
        context_name=context_name,
        context_dir=context_dir or DEFAULT_CONTEXT_DIR,
    )


async def _run_checkpoint_tools(planned: dict[str, Any]) -> dict[str, Any]:
    with _temporary_module_bindings(
        _checkpoint_service,
        create_adapter=create_adapter,
        load_config=load_config,
    ):
        return await _checkpoint_service._run_checkpoint_tools(planned)


async def open_target_model(
    session_id: str,
    *,
    model_path: str | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    feature_target_text: str = "",
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    with _temporary_module_bindings(
        _model_service,
        create_adapter=create_adapter,
        load_config=load_config,
    ):
        return await _model_service.open_target_model(
            session_id,
            model_path=model_path,
            uploaded_files=uploaded_files,
            feature_target_text=feature_target_text,
            db_path=db_path,
            api_origin=api_origin,
        )


def fetch_docs_context(
    session_id: str,
    *,
    docs_query: str = "",
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    with _temporary_module_bindings(
        _docs_service,
        urlopen=urlopen,
    ):
        return _docs_service.fetch_docs_context(
            session_id,
            docs_query=docs_query,
            db_path=db_path,
            api_origin=api_origin,
        )


async def execute_next_checkpoint(
    session_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    with (
        _temporary_module_bindings(
            _session_service,
            ensure_dashboard_session=ensure_dashboard_session,  # noqa: F405
            build_dashboard_state=build_dashboard_state,  # noqa: F405
        ),
        _temporary_module_bindings(
            _checkpoint_service,
            list_plan_checkpoints=list_plan_checkpoints,
            merge_metadata=_merge_metadata,
        ),
    ):
        return await _checkpoint_service.execute_next_checkpoint(
            session_id, db_path=db_path
        )


async def refresh_preview(
    session_id: str,
    *,
    orientation: str = DEFAULT_PREVIEW_ORIENTATION,
    db_path: Path | None = None,
    preview_dir: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    with _temporary_module_bindings(
        _preview_service,
        create_adapter=create_adapter,
        load_config=load_config,
    ):
        return await _preview_service.refresh_preview(
            session_id,
            orientation=orientation,
            db_path=db_path,
            preview_dir=preview_dir,
            api_origin=api_origin,
        )


async def connect_target_model(
    session_id: str,
    *,
    model_path: str | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    feature_target_text: str = "",
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    with (
        _temporary_module_bindings(
            _model_service,
            create_adapter=create_adapter,
            load_config=load_config,
            refresh_preview=refresh_preview,
        ),
        _temporary_module_bindings(
            _preview_service,
            create_adapter=create_adapter,
            load_config=load_config,
        ),
    ):
        return await _model_service.connect_target_model(
            session_id,
            model_path=model_path,
            uploaded_files=uploaded_files,
            feature_target_text=feature_target_text,
            db_path=db_path,
            api_origin=api_origin,
        )


def ingest_reference_source(
    session_id: str,
    *,
    source_path: str,
    namespace: str,
    chunk_size: int = 1200,
    overlap: int = 200,
    db_path: Path | None = None,
) -> dict[str, Any]:
    with _temporary_module_bindings(
        _docs_service,
        _chunk_text=_chunk_text,
        read_reference_url=_read_reference_url,
        read_reference_source=_read_reference_source,
    ):
        return _docs_service.ingest_reference_source(
            session_id,
            source_path=source_path,
            namespace=namespace,
            chunk_size=chunk_size,
            overlap=overlap,
            db_path=db_path,
        )


async def request_clarifications(
    session_id: str,
    user_goal: str,
    *,
    user_answer: str = "",
    model_name: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    async def _compat_run_structured_agent(*args: Any, **kwargs: Any):
        result = await _run_structured_agent(*args, **kwargs)
        if isinstance(result, RecoverableFailure):
            return _llm_service.RecoverableFailure(
                explanation=str(getattr(result, "explanation", "")),
                remediation_steps=list(getattr(result, "remediation_steps", []) or []),
                retry_focus=str(getattr(result, "retry_focus", "")) or "",
                should_retry=bool(getattr(result, "should_retry", False)),
            )
        if all(
            hasattr(result, name)
            for name in (
                "explanation",
                "remediation_steps",
                "retry_focus",
                "should_retry",
            )
        ):
            return _llm_service.RecoverableFailure(
                explanation=str(getattr(result, "explanation", "")),
                remediation_steps=list(getattr(result, "remediation_steps", []) or []),
                retry_focus=str(getattr(result, "retry_focus", "")),
                should_retry=bool(getattr(result, "should_retry", False)),
            )
        return result

    with _temporary_module_bindings(
        _llm_service, _run_structured_agent=_compat_run_structured_agent
    ):
        return await _llm_service.request_clarifications(
            session_id,
            user_goal,
            user_answer=user_answer,
            model_name=model_name,
            db_path=db_path,
        )


async def inspect_family(
    session_id: str,
    user_goal: str,
    *,
    model_name: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    async def _compat_run_structured_agent(*args: Any, **kwargs: Any):
        result = await _run_structured_agent(*args, **kwargs)
        if isinstance(result, RecoverableFailure):
            return _llm_service.RecoverableFailure(
                explanation=str(getattr(result, "explanation", "")),
                remediation_steps=list(getattr(result, "remediation_steps", []) or []),
                retry_focus=str(getattr(result, "retry_focus", "")) or "",
                should_retry=bool(getattr(result, "should_retry", False)),
            )
        if all(
            hasattr(result, name)
            for name in (
                "explanation",
                "remediation_steps",
                "retry_focus",
                "should_retry",
            )
        ):
            return _llm_service.RecoverableFailure(
                explanation=str(getattr(result, "explanation", "")),
                remediation_steps=list(getattr(result, "remediation_steps", []) or []),
                retry_focus=str(getattr(result, "retry_focus", "")),
                should_retry=bool(getattr(result, "should_retry", False)),
            )
        return result

    with _temporary_module_bindings(
        _llm_service, _run_structured_agent=_compat_run_structured_agent
    ):
        return await _llm_service.inspect_family(
            session_id,
            user_goal,
            model_name=model_name,
            db_path=db_path,
        )


# Legacy private helper aliases expected by compatibility tests.
_sanitize_model_path_text = _sanitize_model_path_text
_safe_context_name = _safe_context_name
_normalize_feature_targets = _normalize_feature_targets
_sanitize_preview_viewer_url = _sanitize_preview_viewer_url
_sanitize_ui_text = _utils_service.sanitize_ui_text
_provider_from_model_name = _utils_service.provider_from_model_name
_workflow_copy = _utils_service.workflow_copy
_filter_docs_text = _utils_service.filter_docs_text
_feature_target_status = _utils_service.feature_target_status
_feature_grounding_warning_text = _utils_service.feature_grounding_warning_text
_parse_json_blob = _utils_service.parse_json_blob
_trace_json_default = _utils_service._trace_json_default
_looks_like_path_token = _utils_service._looks_like_path_token
_normalize_model_name_for_provider = _utils_service.normalize_model_name_for_provider
_provider_has_credentials = _utils_service.provider_has_credentials
_trace_json = _utils_service.trace_json
_trace_session_row = _utils_service.trace_session_row
_trace_tool_records = _utils_service.trace_tool_records


__all__ = [
    # core shimmed services
    *[name for name in globals() if not name.startswith("__")],
]
