"""State and backend helpers for the Prefab CAD assistant dashboard."""

from __future__ import annotations

import base64
import binascii
import json
import os
import subprocess
import time
from html.parser import HTMLParser
from importlib import import_module
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from loguru import logger
from pydantic import BaseModel, Field

from ..adapters import create_adapter
from ..adapters.base import ExtrusionParameters
from ..agents.history_db import (
    get_design_session,
    insert_evidence_link,
    insert_model_state_snapshot,
    insert_plan_checkpoint,
    insert_tool_call_record,
    list_evidence_links,
    list_model_state_snapshots,
    list_plan_checkpoints,
    list_tool_call_records,
    update_plan_checkpoint,
    upsert_design_session,
)
from ..agents.retrieval_index import _chunk_text
from ..agents.schemas import RecoverableFailure
from ..config import load_config
from ..utils.feature_tree_classifier import classify_feature_tree_snapshot
from .schemas import DashboardCheckpoint, DashboardEvidenceRow, DashboardUIState

try:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
except ImportError:  # pragma: no cover
    Agent = None
    OpenAIChatModel = None
    OpenAIProvider = None

try:
    PdfReader = import_module("pypdf").PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


DEFAULT_SESSION_ID = "prefab-dashboard"
DEFAULT_USER_GOAL = (
    "Design a printable U-bracket assembly for cable routing with M4 hardware."
)
DEFAULT_SOURCE_MODE = "prompt"
DEFAULT_API_ORIGIN = os.getenv("SOLIDWORKS_UI_API_ORIGIN", "http://127.0.0.1:8766")
DEFAULT_PREVIEW_DIR = Path(".solidworks_mcp") / "ui_previews"
DEFAULT_UPLOADED_MODEL_DIR = Path(".solidworks_mcp") / "ui_uploads"
DEFAULT_PREVIEW_ORIENTATION = "current"
DEFAULT_RAG_DIR = Path(".solidworks_mcp") / "rag"
DEFAULT_WORKFLOW_MODE = "unselected"
SUPPORTED_MODEL_UPLOAD_SUFFIXES = {".sldprt", ".sldasm", ".slddrw"}


class ClarificationResponse(BaseModel):
    """LLM response for goal clarification."""

    normalized_brief: str = Field(min_length=10)
    questions: list[str] = Field(default_factory=list)


class CheckpointCandidate(BaseModel):
    """One suggested execution checkpoint."""

    title: str = Field(min_length=3)
    allowed_tools: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=5)


class FamilyInspection(BaseModel):
    """LLM response for family classification."""

    family: str = Field(min_length=3)
    confidence: Literal["low", "medium", "high"]
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checkpoints: list[CheckpointCandidate] = Field(default_factory=list)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            normalized = " ".join(data.split())
            if normalized:
                self._parts.append(normalized)

    def text(self) -> str:
        return "\n".join(self._parts)


def ensure_preview_dir(preview_dir: Path | None = None) -> Path:
    """Create and return the preview image directory."""
    resolved = preview_dir or DEFAULT_PREVIEW_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def ensure_uploaded_model_dir(upload_dir: Path | None = None) -> Path:
    """Create and return the uploaded-model staging directory."""
    resolved = upload_dir or DEFAULT_UPLOADED_MODEL_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _parse_json_blob(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sanitize_ui_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    if text in {'"', "'"}:
        return fallback
    if text.startswith("{{") and text.endswith("}}"):
        return fallback
    if "$result." in text or "$error" in text:
        return fallback
    return text


def _sanitize_preview_viewer_url(
    value: Any,
    *,
    session_id: str,
    api_origin: str,
) -> str:
    text = _sanitize_ui_text(value, "")
    if not text:
        return ""
    parsed = urlparse(text)
    path = (parsed.path or "").rstrip("/")
    expected_path = f"/api/ui/viewer/{session_id}".rstrip("/")
    if path != expected_path:
        return ""
    if parsed.scheme and parsed.netloc:
        expected = urlparse(api_origin)
        if expected.netloc and parsed.netloc and parsed.netloc != expected.netloc:
            return ""
    return text


def _merge_metadata(
    session_id: str,
    *,
    db_path: Path | None = None,
    user_goal: str | None = None,
    **updates: Any,
) -> dict[str, Any]:
    session_row = get_design_session(session_id, db_path=db_path)
    metadata = _parse_json_blob(session_row["metadata_json"]) if session_row else {}
    metadata.update(updates)

    effective_goal = user_goal or (
        session_row["user_goal"] if session_row else DEFAULT_USER_GOAL
    )
    effective_source = (
        session_row["source_mode"] if session_row else DEFAULT_SOURCE_MODE
    )
    effective_family = session_row["accepted_family"] if session_row else None
    effective_status = session_row["status"] if session_row else "active"
    effective_index = session_row["current_checkpoint_index"] if session_row else 0

    upsert_design_session(
        session_id=session_id,
        user_goal=effective_goal,
        source_mode=effective_source,
        accepted_family=effective_family,
        status=effective_status,
        current_checkpoint_index=effective_index,
        metadata_json=json.dumps(metadata, ensure_ascii=True),
        db_path=db_path,
    )
    return metadata


def _default_checkpoint_specs() -> list[dict[str, Any]]:
    return [
        {
            "title": "Base profile",
            "goal": "Create the base sketch profile",
            "tools": ["create_sketch", "add_line"],
            "rationale": "Establish the bracket footprint before any 3D feature.",
        },
        {
            "title": "Extrude body",
            "goal": "Create the main bracket body",
            "tools": ["create_extrusion"],
            "rationale": "Turn the approved sketch into the primary solid.",
        },
        {
            "title": "Hole pattern",
            "goal": "Add fastener holes and cable clearance",
            "tools": ["create_sketch", "create_cut"],
            "rationale": "Apply mounting features after the body dimensions are stable.",
        },
        {
            "title": "Clearance verify",
            "goal": "Check fit and interference",
            "tools": ["check_interference"],
            "rationale": "Validate the assembly path before release or print export.",
        },
    ]


def _provider_from_model_name(model_name: str) -> str:
    if model_name.startswith("github:"):
        return "github"
    if model_name.startswith("openai:"):
        return "openai"
    if model_name.startswith("anthropic:"):
        return "anthropic"
    if model_name.startswith("local:"):
        return "local"
    return "custom"


def _default_model_for_profile(provider: str, profile: str) -> str:
    normalized_profile = (profile or "balanced").lower()
    if provider == "local":
        profile_models = {
            "small": "local:google/gemma-3-4b-it",
            "balanced": "local:google/gemma-3-12b-it",
            "large": "local:google/gemma-3-27b-it",
        }
        return profile_models.get(normalized_profile, profile_models["balanced"])

    profile_models = {
        "small": "github:openai/gpt-4.1-mini",
        "balanced": "github:openai/gpt-4.1",
        "large": "github:openai/gpt-4.1",
    }
    return profile_models.get(normalized_profile, profile_models["balanced"])


def _provider_has_credentials(
    model_name: str, local_endpoint: str | None = None
) -> bool:
    provider = _provider_from_model_name(model_name)
    if provider == "github":
        token = os.getenv("GITHUB_API_KEY") or os.getenv("GH_TOKEN")
        return bool(token)
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    if provider == "local":
        return bool(local_endpoint)
    return True


def _normalize_workflow_mode(workflow_mode: str | None) -> str:
    normalized = (workflow_mode or DEFAULT_WORKFLOW_MODE).strip().lower()
    if normalized in {"edit_existing", "new_design"}:
        return normalized
    return DEFAULT_WORKFLOW_MODE


def _workflow_copy(
    workflow_mode: str, active_model_path: str | None = None
) -> tuple[str, str, str]:
    has_active_model = bool(str(active_model_path or "").strip())
    if workflow_mode == "edit_existing":
        return (
            "Editing Existing Part or Assembly",
            "Attach a saved .sldprt or .sldasm file, inspect the feature tree, then describe the feature edits you want.",
            "Choose Workflow -> Attach Model -> Inspect -> Plan -> Execute",
        )
    if workflow_mode == "new_design":
        return (
            "New Design From Scratch",
            "Define the design goal and assumptions first, then inspect the proposed family before executing CAD steps.",
            "Choose Workflow -> Define Goal -> Clarify -> Plan -> Execute",
        )
    if has_active_model:
        return (
            "Choose a Workflow",
            "An active model is already attached. Pick whether you want to keep editing that file or pivot to a new design flow.",
            "Choose Workflow -> Attach Model or Define Goal -> Inspect -> Plan -> Execute",
        )
    return (
        "Choose a Workflow",
        "Choose whether you are attaching an existing SolidWorks file or starting a new design from scratch.",
        "Choose Workflow -> Configure -> Inspect/Clarify -> Plan -> Execute",
    )


def _normalize_feature_targets(feature_target_text: str | None) -> list[str]:
    targets: list[str] = []
    for raw in (feature_target_text or "").replace("\n", ",").split(","):
        normalized = raw.strip()
        if not normalized:
            continue
        targets.append(normalized[1:] if normalized.startswith("@") else normalized)
    return targets


def _feature_target_status(
    features: list[dict[str, Any]], feature_target_text: str | None
) -> tuple[str, list[str], list[str]]:
    requested = _normalize_feature_targets(feature_target_text)
    if not requested:
        return ("No grounded feature target selected.", [], [])

    available = {
        str(feature.get("name") or "").strip().lower(): str(feature.get("name") or "")
        for feature in features
        if str(feature.get("name") or "").strip()
    }
    matched: list[str] = []
    missing: list[str] = []
    for target in requested:
        hit = available.get(target.lower())
        if hit:
            matched.append(hit)
        else:
            missing.append(target)

    if matched and not missing:
        return (
            "Grounded feature target(s): " + ", ".join(f"@{name}" for name in matched),
            matched,
            missing,
        )
    if matched:
        return (
            "Partially grounded target(s): "
            + ", ".join(f"@{name}" for name in matched)
            + " | Missing: "
            + ", ".join(f"@{name}" for name in missing),
            matched,
            missing,
        )
    return (
        "No matching feature targets found for: "
        + ", ".join(f"@{name}" for name in missing),
        matched,
        missing,
    )


def _read_reference_source(source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        if PdfReader is None:
            raise RuntimeError(
                "Install pypdf to ingest PDF sources, or provide a text/markdown file instead."
            )
        reader = PdfReader(str(source_path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()

    return source_path.read_text(encoding="utf-8")


def _is_url_reference(source_path: str) -> bool:
    parsed = urlparse((source_path or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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
        parser = _HTMLTextExtractor()
        parser.feed(decoded)
        return parser.text().strip(), label

    return decoded.strip(), label


def _build_agent_model(model_name: str, local_endpoint: str | None = None) -> Any:
    if model_name.startswith("local:"):
        if OpenAIChatModel is None or OpenAIProvider is None:
            raise RuntimeError("pydantic-ai OpenAI provider support is not installed.")
        resolved_endpoint = local_endpoint or os.getenv(
            "SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"
        )
        provider = OpenAIProvider(
            base_url=resolved_endpoint,
            api_key=os.getenv("LOCAL_OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "local",
        )
        return OpenAIChatModel(model_name.split(":", 1)[1], provider=provider)
    return model_name


def _materialize_uploaded_model(
    session_id: str,
    uploaded_files: list[dict[str, Any]] | None,
) -> Path:
    if not uploaded_files:
        raise RuntimeError("No uploaded model file was provided.")

    upload = uploaded_files[0]
    file_name = Path(str(upload.get("name") or "")).name
    if not file_name:
        raise RuntimeError("Uploaded model is missing a filename.")

    suffix = Path(file_name).suffix.lower()
    if suffix not in SUPPORTED_MODEL_UPLOAD_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_MODEL_UPLOAD_SUFFIXES))
        raise RuntimeError(
            f"Unsupported uploaded model type: {suffix or 'unknown'}. Expected one of {allowed}."
        )

    encoded_data = upload.get("data")
    if not isinstance(encoded_data, str) or not encoded_data.strip():
        raise RuntimeError("Uploaded model is missing file data.")

    try:
        file_bytes = base64.b64decode(encoded_data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("Uploaded model payload is not valid base64 data.") from exc

    target_dir = ensure_uploaded_model_dir() / session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_name
    target_path.write_bytes(file_bytes)
    return target_path


def _compute_readiness(
    metadata: dict[str, Any],
    *,
    db_ready: bool,
) -> dict[str, Any]:
    model_name = _sanitize_ui_text(
        metadata.get("model_name"),
        _resolve_model_name(),
    )
    local_endpoint = _sanitize_ui_text(
        metadata.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )

    provider_configured = _provider_has_credentials(model_name, local_endpoint)

    try:
        config = load_config()
        adapter_mode = str(getattr(config.adapter_type, "value", config.adapter_type))
    except Exception:
        adapter_mode = "unknown"

    preview_dir = ensure_preview_dir()
    preview_ready = preview_dir.exists() and os.access(preview_dir, os.W_OK)

    checks = {
        "provider": provider_configured,
        "adapter": adapter_mode != "unknown",
        "preview": preview_ready,
        "db": db_ready,
    }
    ready_count = sum(1 for value in checks.values() if value)
    summary = (
        f"Readiness {ready_count}/4 | provider={provider_configured} | "
        f"adapter={adapter_mode} | preview={preview_ready} | db={db_ready}"
    )

    return {
        "readiness_provider_configured": provider_configured,
        "readiness_adapter_mode": adapter_mode,
        "readiness_preview_ready": preview_ready,
        "readiness_db_ready": db_ready,
        "readiness_summary": summary,
    }


def _planned_tools(planned: dict[str, Any]) -> list[str]:
    tools = planned.get("tools", [])
    return [str(tool) for tool in tools] if isinstance(tools, list) else []


async def _run_checkpoint_tools(
    planned: dict[str, Any],
) -> dict[str, Any]:
    """Execute supported checkpoint tools through the active adapter.

    Unsupported tools are marked as MOCKED and returned in the summary.
    """
    config = load_config()
    adapter = await create_adapter(config)
    tool_runs: list[dict[str, Any]] = []
    mocked_tools: list[str] = []
    failed_tools: list[str] = []

    try:
        await adapter.connect()
        for tool_name in _planned_tools(planned):
            if tool_name == "create_sketch":
                result = await adapter.create_sketch("Top")
                success = bool(result.is_success)
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "status": "success" if success else "error",
                        "message": "Created sketch on Top plane"
                        if success
                        else str(result.error or "create_sketch failed"),
                    }
                )
                if not success:
                    failed_tools.append(tool_name)
                continue

            if tool_name == "add_line":
                result = await adapter.add_line(0.0, 0.0, 40.0, 0.0)
                success = bool(result.is_success)
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "status": "success" if success else "error",
                        "message": "Added baseline line segment"
                        if success
                        else str(result.error or "add_line failed"),
                    }
                )
                if not success:
                    failed_tools.append(tool_name)
                continue

            if tool_name == "create_extrusion":
                result = await adapter.create_extrusion(ExtrusionParameters(depth=10.0))
                success = bool(result.is_success)
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "status": "success" if success else "error",
                        "message": "Created 10mm extrusion"
                        if success
                        else str(result.error or "create_extrusion failed"),
                    }
                )
                if not success:
                    failed_tools.append(tool_name)
                continue

            if tool_name == "create_cut":
                if hasattr(adapter, "create_cut_extrude"):
                    result = await adapter.create_cut_extrude(
                        ExtrusionParameters(depth=3.0)
                    )
                else:
                    result = await adapter.create_cut("Sketch1", 3.0)
                success = bool(result.is_success)
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "status": "success" if success else "error",
                        "message": "Created 3mm cut feature"
                        if success
                        else str(result.error or "create_cut failed"),
                    }
                )
                if not success:
                    failed_tools.append(tool_name)
                continue

            # MOCKED: No direct adapter method for interference checks yet.
            if tool_name == "check_interference":
                mocked_tools.append(tool_name)
                tool_runs.append(
                    {
                        "tool": tool_name,
                        "status": "mocked",
                        "message": "MOCKED: Requires tool-layer check_interference wiring.",
                    }
                )
                continue

            mocked_tools.append(tool_name)
            tool_runs.append(
                {
                    "tool": tool_name,
                    "status": "mocked",
                    "message": "MOCKED: No adapter binding defined for this tool.",
                }
            )
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


def ensure_dashboard_session(
    session_id: str = DEFAULT_SESSION_ID,
    *,
    user_goal: str = DEFAULT_USER_GOAL,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Ensure one dashboard session row and default checkpoints exist."""
    session_row = get_design_session(session_id, db_path=db_path)
    if session_row is None:
        upsert_design_session(
            session_id=session_id,
            user_goal=user_goal,
            source_mode=DEFAULT_SOURCE_MODE,
            status="inspect",
            metadata_json=json.dumps(
                {
                    "normalized_brief": user_goal,
                    "preview_orientation": DEFAULT_PREVIEW_ORIENTATION,
                },
                ensure_ascii=True,
            ),
            db_path=db_path,
        )
    elif user_goal != session_row["user_goal"]:
        upsert_design_session(
            session_id=session_id,
            user_goal=user_goal,
            source_mode=session_row["source_mode"],
            accepted_family=session_row["accepted_family"],
            status=session_row["status"],
            current_checkpoint_index=session_row["current_checkpoint_index"],
            metadata_json=session_row["metadata_json"],
            db_path=db_path,
        )

    checkpoints = list_plan_checkpoints(session_id, db_path=db_path)
    if not checkpoints:
        for index, spec in enumerate(_default_checkpoint_specs(), start=1):
            insert_plan_checkpoint(
                session_id=session_id,
                checkpoint_index=index,
                title=spec["title"],
                planned_action_json=json.dumps(spec, ensure_ascii=True),
                approved_by_user=index == 1,
                db_path=db_path,
            )

    return get_design_session(session_id, db_path=db_path) or {}


def approve_design_brief(
    session_id: str,
    user_goal: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Persist the accepted goal for the active dashboard session."""
    ensure_dashboard_session(session_id, user_goal=user_goal, db_path=db_path)
    metadata = _merge_metadata(
        session_id,
        db_path=db_path,
        user_goal=user_goal,
        normalized_brief=user_goal,
        latest_message="Brief accepted.",
        latest_error_text="",
        remediation_hint="",
    )
    insert_tool_call_record(
        session_id=session_id,
        tool_name="ui.approve_brief",
        input_json=json.dumps({"user_goal": user_goal}, ensure_ascii=True),
        output_json=json.dumps(metadata, ensure_ascii=True),
        db_path=db_path,
    )
    return build_dashboard_state(session_id, db_path=db_path)


def accept_family_choice(
    session_id: str,
    family: str | None = None,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Accept the proposed family and advance the session."""
    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    accepted_family = family or metadata.get("proposed_family") or "unknown"
    upsert_design_session(
        session_id=session_id,
        user_goal=session_row.get("user_goal") or DEFAULT_USER_GOAL,
        source_mode=session_row.get("source_mode") or DEFAULT_SOURCE_MODE,
        accepted_family=accepted_family,
        status="planned",
        current_checkpoint_index=session_row.get("current_checkpoint_index") or 0,
        metadata_json=session_row.get("metadata_json"),
        db_path=db_path,
    )
    _merge_metadata(
        session_id,
        db_path=db_path,
        accepted_family=accepted_family,
        latest_message=f"Family accepted: {accepted_family}.",
        latest_error_text="",
        remediation_hint="",
    )
    insert_tool_call_record(
        session_id=session_id,
        tool_name="ui.accept_family",
        input_json=json.dumps({"family": accepted_family}, ensure_ascii=True),
        success=True,
        db_path=db_path,
    )
    return build_dashboard_state(session_id, db_path=db_path)


async def execute_next_checkpoint(
    session_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Execute the next pending checkpoint and persist detailed run status."""
    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    checkpoints = list_plan_checkpoints(session_id, db_path=db_path)
    target = next((row for row in checkpoints if not row["executed"]), None)
    if target is None:
        _merge_metadata(
            session_id,
            db_path=db_path,
            latest_message="All checkpoints have already been executed.",
        )
        return build_dashboard_state(session_id, db_path=db_path)

    planned = _parse_json_blob(target["planned_action_json"])
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
    _merge_metadata(
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


def reconcile_manual_edits(
    session_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Compare the latest two snapshots and summarize the reconciliation step."""
    ensure_dashboard_session(session_id, db_path=db_path)
    snapshots = list_model_state_snapshots(session_id, db_path=db_path)

    if len(snapshots) < 2:
        message = (
            "Not enough snapshots yet. Capture another preview after manual edits."
        )
    else:
        latest = snapshots[0]
        previous = snapshots[1]
        changed = latest.get("state_fingerprint") != previous.get(
            "state_fingerprint"
        ) or latest.get("screenshot_path") != previous.get("screenshot_path")
        if changed:
            message = "Detected manual changes. Options: accept edits, patch toward goal, or rollback."
        else:
            message = (
                "No visual/state change detected since the last accepted snapshot."
            )

    insert_tool_call_record(
        session_id=session_id,
        tool_name="ui.reconcile_manual_edits",
        output_json=json.dumps({"message": message}, ensure_ascii=True),
        success=True,
        db_path=db_path,
    )
    _merge_metadata(session_id, db_path=db_path, latest_message=message)
    return build_dashboard_state(session_id, db_path=db_path)


def update_ui_preferences(
    session_id: str,
    *,
    assumptions_text: str | None = None,
    model_provider: str | None = None,
    model_profile: str | None = None,
    model_name: str | None = None,
    local_endpoint: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Persist editable assumptions and model/provider preferences."""
    ensure_dashboard_session(session_id, db_path=db_path)
    provider = (model_provider or "github").strip().lower()
    profile = (model_profile or "balanced").strip().lower()
    resolved_model = _sanitize_ui_text(
        model_name,
        _default_model_for_profile(provider, profile),
    )
    resolved_endpoint = _sanitize_ui_text(
        local_endpoint,
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )
    metadata = _merge_metadata(
        session_id,
        db_path=db_path,
        assumptions_text=_sanitize_ui_text(
            assumptions_text,
            "No assumptions provided yet.",
        ),
        model_provider=provider,
        model_profile=profile,
        model_name=resolved_model,
        local_endpoint=resolved_endpoint,
        latest_message="Updated assumptions and model preferences.",
        latest_error_text="",
        remediation_hint="",
    )
    insert_tool_call_record(
        session_id=session_id,
        tool_name="ui.update_preferences",
        input_json=json.dumps(
            {
                "assumptions_text": assumptions_text,
                "model_provider": provider,
                "model_profile": profile,
                "model_name": resolved_model,
                "local_endpoint": resolved_endpoint,
            },
            ensure_ascii=True,
        ),
        output_json=json.dumps(metadata, ensure_ascii=True),
        success=True,
        db_path=db_path,
    )
    return build_dashboard_state(session_id, db_path=db_path)


def select_workflow_mode(
    session_id: str,
    *,
    workflow_mode: str,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Persist the onboarding workflow branch for the active dashboard session."""
    ensure_dashboard_session(session_id, db_path=db_path)
    normalized_mode = _normalize_workflow_mode(workflow_mode)
    workflow_label, workflow_guidance, _ = _workflow_copy(normalized_mode)
    metadata = _merge_metadata(
        session_id,
        db_path=db_path,
        workflow_mode=normalized_mode,
        latest_message=f"Workflow selected: {workflow_label}.",
        latest_error_text="",
        remediation_hint="",
    )
    insert_tool_call_record(
        session_id=session_id,
        tool_name="ui.select_workflow_mode",
        input_json=json.dumps({"workflow_mode": normalized_mode}, ensure_ascii=True),
        output_json=json.dumps(
            {
                "workflow_mode": normalized_mode,
                "workflow_label": workflow_label,
                "workflow_guidance_text": workflow_guidance,
                "metadata": metadata,
            },
            ensure_ascii=True,
        ),
        success=True,
        db_path=db_path,
    )
    return build_dashboard_state(session_id, db_path=db_path)


async def connect_target_model(
    session_id: str,
    *,
    model_path: str | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    feature_target_text: str | None = None,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Open a target model, inspect its feature tree, and persist grounded context."""
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

    if uploaded_files:
        try:
            resolved_path = _materialize_uploaded_model(session_id, uploaded_files)
        except RuntimeError as exc:
            _merge_metadata(
                session_id,
                db_path=db_path,
                latest_message="Uploaded model could not be prepared.",
                latest_error_text=str(exc),
                remediation_hint="Choose a valid .sldprt or .sldasm file and retry.",
                feature_target_text=feature_target_text or "",
                workflow_mode="edit_existing",
            )
            return build_dashboard_state(
                session_id, db_path=db_path, api_origin=api_origin
            )
    elif model_path:
        resolved_path = Path(model_path).expanduser()
    else:
        _merge_metadata(
            session_id,
            db_path=db_path,
            latest_message="No target model was provided.",
            latest_error_text="Missing model path or uploaded model file.",
            remediation_hint="Choose a local SolidWorks file or provide an absolute model path.",
            feature_target_text=feature_target_text or "",
            workflow_mode="edit_existing",
        )
        return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)

    assert resolved_path is not None
    if not resolved_path.exists():
        _merge_metadata(
            session_id,
            db_path=db_path,
            latest_message="Target model path was not found.",
            latest_error_text=f"Missing file: {resolved_path}",
            remediation_hint="Provide an absolute path to an existing .sldprt or .sldasm file.",
            active_model_path=str(resolved_path),
            feature_target_text=feature_target_text or "",
            workflow_mode="edit_existing",
        )
        return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)

    config = load_config()
    adapter = await create_adapter(config)
    model_info: dict[str, Any] = {}
    features: list[dict[str, Any]] = []
    preview_status_message = ""
    tool_input = {
        "model_path": str(resolved_path.resolve()),
        "uploaded_file_name": uploaded_files[0].get("name") if uploaded_files else None,
        "feature_target_text": feature_target_text or "",
    }
    try:
        await adapter.connect()
        logger.info(
            "[ui.connect_target_model] opening model path={} ",
            str(resolved_path.resolve()),
        )
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

        classification = classify_feature_tree_snapshot(model_info, features)
        target_status, matched_targets, missing_targets = _feature_target_status(
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

        preview_path = ensure_preview_dir() / f"{session_id}.png"
        if hasattr(adapter, "export_image"):
            logger.info(
                "[ui.connect_target_model] exporting preview to {}",
                str(preview_path.resolve()),
            )
            export_result = await adapter.export_image(
                {
                    "file_path": str(preview_path.resolve()),
                    "format_type": "png",
                    "width": 1280,
                    "height": 720,
                    "view_orientation": DEFAULT_PREVIEW_ORIENTATION,
                }
            )
            if export_result.is_success:
                preview_status_message = "Attached model and refreshed preview."
                logger.info(
                    "[ui.connect_target_model] preview export succeeded path={}",
                    str(preview_path.resolve()),
                )
                insert_model_state_snapshot(
                    session_id=session_id,
                    model_path=str(resolved_path.resolve()),
                    screenshot_path=str(preview_path.resolve()),
                    state_fingerprint=f"preview::{preview_path.stat().st_mtime_ns}",
                    db_path=db_path,
                )

        # Export STL for interactive 3D viewer
        stl_path = ensure_preview_dir() / f"{session_id}.stl"
        viewer_ts = int(time.time())
        if hasattr(adapter, "export_file"):
            try:
                stl_result = await adapter.export_file(str(stl_path.resolve()), "stl")
                if stl_result.is_success and stl_path.exists():
                    viewer_ts = int(stl_path.stat().st_mtime)
                    logger.info(
                        "[ui.connect_target_model] STL export succeeded path={}",
                        str(stl_path.resolve()),
                    )
            except Exception:
                logger.debug(
                    "[ui.connect_target_model] STL export skipped (adapter error)"
                )
        preview_viewer_url = f"{api_origin}/api/ui/viewer/{session_id}?session_id={session_id}&t={viewer_ts}"

        metadata = _merge_metadata(
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
                preview_status_message
                or f"Attached target model {resolved_path.name} for planning and feature edits."
            ),
            preview_viewer_url=preview_viewer_url,
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
    except Exception as exc:
        logger.exception(
            "[ui.connect_target_model] failed session_id={} path={} error={}",
            session_id,
            str(resolved_path.resolve()) if resolved_path else "<none>",
            exc,
        )
        _merge_metadata(
            session_id,
            db_path=db_path,
            workflow_mode="edit_existing",
            active_model_path=str(resolved_path.resolve()),
            feature_target_text=feature_target_text or "",
            latest_message="Failed to attach target model.",
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
    finally:
        if adapter is not None:
            try:
                await adapter.disconnect()
            except Exception:
                logger.debug("Adapter disconnect failed during target-model cleanup")

    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def ingest_reference_source(
    session_id: str,
    *,
    source_path: str,
    namespace: str,
    chunk_size: int = 1200,
    overlap: int = 200,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Ingest a user-provided local file or URL into a simple local retrieval index."""
    ensure_dashboard_session(session_id, db_path=db_path)
    source_reference = (source_path or "").strip()
    resolved_namespace = (
        namespace or "engineering-reference"
    ).strip() or "engineering-reference"

    try:
        if _is_url_reference(source_reference):
            source_identifier = source_reference
            source_text, source_label = _read_reference_url(source_reference)
        else:
            resolved_source = Path(source_reference).expanduser()
            if not resolved_source.exists():
                _merge_metadata(
                    session_id,
                    db_path=db_path,
                    rag_source_path=str(resolved_source),
                    rag_namespace=resolved_namespace,
                    rag_status="Reference source path was not found.",
                    latest_error_text=f"Missing reference source: {resolved_source}",
                    remediation_hint="Provide an absolute path or an http/https URL for a PDF, markdown, text, or HTML source.",
                )
                return build_dashboard_state(session_id, db_path=db_path)
            source_identifier = str(resolved_source.resolve())
            source_label = resolved_source.name
            source_text = _read_reference_source(resolved_source)

        chunks = _chunk_text(source_text, chunk_size=chunk_size, overlap=overlap)
        output_path = DEFAULT_RAG_DIR / f"{resolved_namespace}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1.0",
            "namespace": resolved_namespace,
            "source_location": source_identifier,
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "id": f"{resolved_namespace}-{index}",
                    "source": source_identifier,
                    "text": chunk,
                }
                for index, chunk in enumerate(chunks, start=1)
            ],
        }
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        insert_evidence_link(
            session_id=session_id,
            source_type="rag_ingest",
            source_id=source_identifier,
            relevance_score=0.88,
            rationale=f"Ingested {len(chunks)} chunk(s) into namespace '{resolved_namespace}'.",
            payload_json=json.dumps(
                {
                    "namespace": resolved_namespace,
                    "index_path": str(output_path.resolve()),
                    "chunk_count": len(chunks),
                },
                ensure_ascii=True,
            ),
            db_path=db_path,
        )
        _merge_metadata(
            session_id,
            db_path=db_path,
            rag_source_path=source_identifier,
            rag_namespace=resolved_namespace,
            rag_status=f"Ingested {len(chunks)} chunk(s) from {source_label}.",
            rag_index_path=str(output_path.resolve()),
            rag_chunk_count=len(chunks),
            rag_provenance_text=(
                f"Namespace {resolved_namespace} | source {source_label} | chunks {len(chunks)}"
            ),
            latest_message=f"Reference source {source_label} ingested for retrieval.",
            latest_error_text="",
            remediation_hint="",
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.ingest_reference_source",
            input_json=json.dumps(
                {
                    "source_path": source_identifier,
                    "namespace": resolved_namespace,
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                },
                ensure_ascii=True,
            ),
            output_json=json.dumps(
                {
                    "index_path": str(output_path.resolve()),
                    "chunk_count": len(chunks),
                },
                ensure_ascii=True,
            ),
            success=True,
            db_path=db_path,
        )
    except Exception as exc:
        _merge_metadata(
            session_id,
            db_path=db_path,
            rag_source_path=source_reference,
            rag_namespace=resolved_namespace,
            rag_status="Reference ingestion failed.",
            latest_error_text=str(exc),
            remediation_hint="Use a readable local file or http/https URL and ensure optional PDF dependencies are installed.",
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.ingest_reference_source",
            input_json=json.dumps(
                {
                    "source_path": source_reference,
                    "namespace": resolved_namespace,
                },
                ensure_ascii=True,
            ),
            output_json=json.dumps({"error": str(exc)}, ensure_ascii=True),
            success=False,
            db_path=db_path,
        )

    return build_dashboard_state(session_id, db_path=db_path)


def _resolve_model_name(explicit_model: str | None = None) -> str:
    return explicit_model or os.getenv("SOLIDWORKS_UI_MODEL", "github:openai/gpt-4.1")


def _ensure_provider_credentials(
    model_name: str, local_endpoint: str | None = None
) -> None:
    if model_name.startswith("github:"):
        github_token = os.getenv("GITHUB_API_KEY") or os.getenv("GH_TOKEN")
        if not github_token:
            try:
                result = subprocess.run(
                    ["gh", "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except Exception:
                result = None
            if result and result.returncode == 0:
                github_token = result.stdout.strip()
        if not github_token:
            raise RuntimeError(
                "Set GH_TOKEN or GITHUB_API_KEY with models:read scope before using the dashboard LLM actions."
            )
        os.environ.setdefault("GITHUB_API_KEY", github_token)
        return

    if model_name.startswith("openai:") and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before using OpenAI model routing.")

    if model_name.startswith("anthropic:") and not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "Set ANTHROPIC_API_KEY before using Anthropic model routing."
        )

    if model_name.startswith("local:"):
        resolved_endpoint = local_endpoint or os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT")
        if not resolved_endpoint:
            raise RuntimeError(
                "Set SOLIDWORKS_UI_LOCAL_ENDPOINT before using local model routing."
            )


async def _run_structured_agent(
    *,
    system_prompt: str,
    user_prompt: str,
    result_type: type[BaseModel],
    model_name: str | None = None,
    local_endpoint: str | None = None,
) -> BaseModel | RecoverableFailure:
    if Agent is None:  # pragma: no cover
        return RecoverableFailure(
            explanation="pydantic_ai is not installed in this environment.",
            remediation_steps=["Install project dependencies and retry."],
            retry_focus="Install pydantic-ai and a supported provider.",
            should_retry=False,
        )

    resolved_model = _resolve_model_name(model_name)
    resolved_endpoint = local_endpoint or os.getenv(
        "SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"
    )
    _ensure_provider_credentials(resolved_model, resolved_endpoint)
    configured_model = _build_agent_model(
        resolved_model,
        resolved_endpoint,
    )
    agent = Agent(
        configured_model,
        system_prompt=system_prompt,
        output_type=[result_type, RecoverableFailure],
    )
    result = await agent.run(user_prompt)
    payload = result.data if hasattr(result, "data") else result.output
    if isinstance(payload, RecoverableFailure):
        return payload
    return (
        payload
        if isinstance(payload, result_type)
        else result_type.model_validate(payload)
    )


async def request_clarifications(
    session_id: str,
    user_goal: str,
    *,
    user_answer: str = "",
    db_path: Path | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """
    Generate focused follow-up questions for the current design goal using LLM.

    Calls GitHub Copilot (openai/gpt-4.1) by default or a model specified in SOLIDWORKS_UI_MODEL env.
    Requires GH_TOKEN or GITHUB_API_KEY with models:read scope.
    """
    ensure_dashboard_session(session_id, user_goal=user_goal, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    resolved_model_name = _sanitize_ui_text(
        model_name or metadata.get("model_name"),
        _resolve_model_name(),
    )
    resolved_local_endpoint = _sanitize_ui_text(
        metadata.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )
    answer_section = (
        f"\nUser's answers/clarifications: {user_answer}" if user_answer else ""
    )
    prompt = (
        "You are preparing a SolidWorks design brief. Return a normalized brief and at most three "
        "clarifying questions that unblock modeling.\n\n"
        f"User goal: {user_goal}\n"
        f"Active model path: {metadata.get('active_model_path', '')}\n"
        f"Feature target refs: {metadata.get('feature_target_text', '')}\n"
        f"Reference corpus: {metadata.get('rag_provenance_text', '')}"
        f"{answer_section}"
    )
    # LLM Call: GitHub Copilot for plan clarification
    result = await _run_structured_agent(
        system_prompt=(
            "You are a CAD planning assistant. Ask only the highest-leverage questions and normalize "
            "the brief into concise manufacturing-ready language."
        ),
        user_prompt=prompt,
        result_type=ClarificationResponse,
        model_name=resolved_model_name,
        local_endpoint=resolved_local_endpoint,
    )

    if isinstance(result, RecoverableFailure):
        _merge_metadata(
            session_id,
            db_path=db_path,
            latest_message=result.explanation,
            clarifying_questions=[],
            latest_error_text=result.explanation,
            remediation_hint=(
                result.remediation_steps[0]
                if result.remediation_steps
                else "Configure provider credentials and retry."
            ),
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.request_clarifications",
            input_json=json.dumps({"user_goal": user_goal}, ensure_ascii=True),
            output_json=result.model_dump_json(),
            success=False,
            db_path=db_path,
        )
        return build_dashboard_state(session_id, db_path=db_path)

    metadata = _merge_metadata(
        session_id,
        db_path=db_path,
        user_goal=user_goal,
        normalized_brief=result.normalized_brief,
        clarifying_questions=result.questions,
        user_clarification_answer=user_answer,
        latest_message="Generated clarifying questions from GitHub Copilot.",
        latest_error_text="",
        remediation_hint="",
    )
    insert_tool_call_record(
        session_id=session_id,
        tool_name="ui.request_clarifications",
        input_json=json.dumps({"user_goal": user_goal}, ensure_ascii=True),
        output_json=result.model_dump_json(),
        success=True,
        db_path=db_path,
    )
    insert_evidence_link(
        session_id=session_id,
        source_type="llm",
        source_id="clarification_response",
        relevance_score=0.9,
        rationale="Normalized brief and follow-up questions from GitHub Copilot.",
        payload_json=json.dumps(metadata, ensure_ascii=True),
        db_path=db_path,
    )
    return build_dashboard_state(session_id, db_path=db_path)


async def inspect_family(
    session_id: str,
    user_goal: str,
    *,
    db_path: Path | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """
    Run LLM-backed family classification and suggested checkpoints.

    Calls GitHub Copilot to infer the likely SolidWorks feature family
    (e.g., "bracket", "housing", "fastener", "assembly") and suggests
    4 conservative checkpoints with allowed MCP tools.
    """
    ensure_dashboard_session(session_id, user_goal=user_goal, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    resolved_model_name = _sanitize_ui_text(
        model_name or metadata.get("model_name"),
        _resolve_model_name(),
    )
    resolved_local_endpoint = _sanitize_ui_text(
        metadata.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )
    prompt = (
        "Classify the likely SolidWorks feature family for this goal and suggest up to four conservative "
        "checkpoints. Prefer direct MCP tools when possible.\n\n"
        f"Design goal: {user_goal}\n"
        f"Active model path: {metadata.get('active_model_path', '')}\n"
        f"Active model status: {metadata.get('active_model_status', '')}\n"
        f"Feature target refs: {metadata.get('feature_target_text', '')}\n"
        f"Feature target status: {metadata.get('feature_target_status', '')}\n"
        f"Reference corpus: {metadata.get('rag_provenance_text', '')}\n"
        f"Local classifier family: {metadata.get('proposed_family', '')}\n"
        f"Local classifier evidence: {' | '.join(metadata.get('family_evidence', []))}"
    )
    # LLM Call: GitHub Copilot for family classification
    result = await _run_structured_agent(
        system_prompt=(
            "You are a SolidWorks routing assistant. Return a family, confidence, evidence, warnings, "
            "and checkpoint plan suitable for a human-reviewed build."
        ),
        user_prompt=prompt,
        result_type=FamilyInspection,
        model_name=resolved_model_name,
        local_endpoint=resolved_local_endpoint,
    )

    if isinstance(result, RecoverableFailure):
        _merge_metadata(
            session_id,
            db_path=db_path,
            latest_message=result.explanation,
            latest_error_text=result.explanation,
            remediation_hint=(
                result.remediation_steps[0]
                if result.remediation_steps
                else "Adjust provider/model settings, then retry inspect."
            ),
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="ui.inspect_family",
            input_json=json.dumps({"user_goal": user_goal}, ensure_ascii=True),
            output_json=result.model_dump_json(),
            success=False,
            db_path=db_path,
        )
        return build_dashboard_state(session_id, db_path=db_path)

    evidence_payload = []
    for index, line in enumerate(result.evidence, start=1):
        insert_evidence_link(
            session_id=session_id,
            source_type="llm",
            source_id=f"family_evidence_{index}",
            relevance_score=0.85,
            rationale=line,
            payload_json=json.dumps({"family": result.family}, ensure_ascii=True),
            db_path=db_path,
        )
        evidence_payload.append(line)

    existing = list_plan_checkpoints(session_id, db_path=db_path)
    if not existing and result.checkpoints:
        for index, checkpoint in enumerate(result.checkpoints, start=1):
            insert_plan_checkpoint(
                session_id=session_id,
                checkpoint_index=index,
                title=checkpoint.title,
                planned_action_json=json.dumps(
                    {
                        "title": checkpoint.title,
                        "goal": checkpoint.title,
                        "tools": checkpoint.allowed_tools,
                        "rationale": checkpoint.rationale,
                    },
                    ensure_ascii=True,
                ),
                approved_by_user=index == 1,
                db_path=db_path,
            )

    metadata = _merge_metadata(
        session_id,
        db_path=db_path,
        user_goal=user_goal,
        proposed_family=result.family,
        family_confidence=result.confidence,
        family_evidence=evidence_payload,
        family_warnings=result.warnings,
        latest_message=f"Updated family classification to '{result.family}' from GitHub Copilot.",
        latest_error_text="",
        remediation_hint="",
    )
    insert_tool_call_record(
        session_id=session_id,
        tool_name="ui.inspect_family",
        input_json=json.dumps({"user_goal": user_goal}, ensure_ascii=True),
        output_json=result.model_dump_json(),
        success=True,
        db_path=db_path,
    )
    insert_evidence_link(
        session_id=session_id,
        source_type="llm",
        source_id="family_inspection",
        relevance_score=0.93,
        rationale="LLM family classification and checkpoint suggestions from GitHub Copilot.",
        payload_json=json.dumps(metadata, ensure_ascii=True),
        db_path=db_path,
    )
    return build_dashboard_state(session_id, db_path=db_path)


def _public_preview_url(
    preview_path: Path,
    *,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> str:
    timestamp = (
        int(preview_path.stat().st_mtime) if preview_path.exists() else int(time.time())
    )
    return f"{api_origin}/previews/{preview_path.name}?ts={timestamp}"


async def refresh_preview(
    session_id: str,
    *,
    orientation: str = DEFAULT_PREVIEW_ORIENTATION,
    db_path: Path | None = None,
    preview_dir: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """
    Export the current SolidWorks viewport to a PNG preview and STL for the 3D viewer.

    Uses export_image(view_orientation=...) from the active adapter.
    Supports orientations: "front", "top", "right", "isometric", "current".
    Also exports an STL file to power the embedded Three.js viewer.
    """
    ensure_dashboard_session(session_id, db_path=db_path)
    logger.info(
        "[ui.refresh_preview] session_id={} orientation={}",
        session_id,
        orientation,
    )
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    preview_viewer_url = _sanitize_preview_viewer_url(
        metadata.get("preview_viewer_url"),
        session_id=session_id,
        api_origin=api_origin,
    )
    resolved_preview_dir = ensure_preview_dir(preview_dir)
    preview_path = resolved_preview_dir / f"{session_id}.png"

    try:
        config = load_config()
        adapter = await create_adapter(config)
        await adapter.connect()
        active_model_path = metadata.get("active_model_path")
        if active_model_path and hasattr(adapter, "open_model"):
            candidate_path = Path(str(active_model_path))
            if candidate_path.exists():
                logger.info(
                    "[ui.refresh_preview] reopening active model {}",
                    str(candidate_path.resolve()),
                )
                await adapter.open_model(str(candidate_path.resolve()))
        payload = {
            "file_path": str(preview_path.resolve()),
            "format_type": "png",
            "width": 1280,
            "height": 720,
            "view_orientation": orientation,
        }
        if not hasattr(adapter, "export_image"):
            # MOCKED: Graceful fallback if adapter doesn't support export_image
            raise RuntimeError("Active adapter does not support export_image.")

        result = await adapter.export_image(payload)
        if not result.is_success:
            raise RuntimeError(result.error or "Failed to export current view.")
        logger.info(
            "[ui.refresh_preview] PNG export succeeded file_path={}",
            str(preview_path.resolve()),
        )

        # Export STL for the interactive 3D viewer
        stl_path = resolved_preview_dir / f"{session_id}.stl"
        viewer_ts = int(time.time())
        if hasattr(adapter, "export_file"):
            try:
                stl_result = await adapter.export_file(str(stl_path.resolve()), "stl")
                if stl_result.is_success and stl_path.exists():
                    viewer_ts = int(stl_path.stat().st_mtime)
                    logger.info(
                        "[ui.refresh_preview] STL export succeeded path={}",
                        str(stl_path.resolve()),
                    )
            except Exception:
                logger.debug("[ui.refresh_preview] STL export skipped (adapter error)")
        preview_viewer_url = f"{api_origin}/api/ui/viewer/{session_id}?t={viewer_ts}"

        await adapter.disconnect()

        snapshot_id = insert_model_state_snapshot(
            session_id=session_id,
            screenshot_path=str(preview_path.resolve()),
            state_fingerprint=f"preview-{preview_path.stat().st_mtime_ns}",
            db_path=db_path,
        )
        insert_tool_call_record(
            session_id=session_id,
            tool_name="export_image",
            input_json=json.dumps(payload, ensure_ascii=True),
            output_json=json.dumps(result.data or {}, ensure_ascii=True),
            success=True,
            db_path=db_path,
        )
        _merge_metadata(
            session_id,
            db_path=db_path,
            preview_orientation=orientation,
            latest_message="Preview refreshed. 3D view updated.",
            latest_snapshot_id=snapshot_id,
            preview_viewer_url=preview_viewer_url,
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
        _merge_metadata(
            session_id,
            db_path=db_path,
            latest_message=(
                "Preview refresh failed. Ensure SolidWorks is open with an active model; the dashboard uses "
                "export_image(view_orientation='current') rather than an embedded viewport API."
            ),
            preview_orientation=orientation,
            preview_viewer_url="",
            latest_error_text=str(exc),
            remediation_hint="Open a model in SolidWorks and retry preview refresh.",
        )

    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def build_dashboard_state(
    session_id: str = DEFAULT_SESSION_ID,
    *,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Assemble the dashboard payload consumed by the Prefab UI."""
    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    db_ready = bool(session_row)

    checkpoints = []
    for row in list_plan_checkpoints(session_id, db_path=db_path):
        planned = _parse_json_blob(row["planned_action_json"])
        result_payload = _parse_json_blob(row.get("result_json"))
        if result_payload.get("status") == "error":
            status = "failed"
        elif row["executed"]:
            status = "executed"
        elif row["approved_by_user"]:
            status = "approved"
        else:
            status = "queued"

        mocked_tools = result_payload.get("mocked_tools", [])
        tools_text = ", ".join(_planned_tools(planned))
        if mocked_tools:
            tools_text = f"{tools_text} [MOCKED: {', '.join(mocked_tools)}]"

        checkpoints.append(
            DashboardCheckpoint(
                step=str(row["checkpoint_index"]),
                goal=planned.get("goal") or row["title"],
                tools=tools_text,
                status=status,
            ).model_dump()
        )

    structured_rendering_enabled = bool(checkpoints)

    checkpoints_text = (
        " | ".join(
            f"{item['step']}. {item['goal']} [{item['status']}] via {item['tools']}"
            for item in checkpoints
        )
        if checkpoints
        else "No checkpoints available yet."
    )

    evidence_rows = []
    for evidence in list_evidence_links(session_id, db_path=db_path)[-6:]:
        evidence_rows.append(
            DashboardEvidenceRow(
                source=evidence["source_type"],
                detail=evidence["rationale"] or evidence["source_id"],
                score=(
                    f"{evidence['relevance_score']:.2f}"
                    if evidence["relevance_score"] is not None
                    else "-"
                ),
            ).model_dump()
        )

    evidence_rows_text = (
        " | ".join(
            f"{item['source']}: {item['detail']} (score {item['score']})"
            for item in evidence_rows
        )
        if evidence_rows
        else "No evidence links captured yet."
    )

    tool_history = list_tool_call_records(session_id, db_path=db_path)
    latest_tool = tool_history[-1]["tool_name"] if tool_history else "waiting"

    preview_url = ""
    preview_status = "No preview captured yet."
    snapshots = list_model_state_snapshots(session_id, db_path=db_path)
    latest_snapshot_path = snapshots[0].get("screenshot_path") if snapshots else None
    if latest_snapshot_path:
        preview_path = Path(latest_snapshot_path)
        if preview_path.exists():
            preview_url = _public_preview_url(preview_path, api_origin=api_origin)
            preview_status = (
                f"Synced from SolidWorks current view. Last file: {preview_path.name}"
            )

    # 3D viewer URL: read from metadata (set when model connects or preview refreshes)
    preview_viewer_url = _sanitize_preview_viewer_url(
        metadata.get("preview_viewer_url"),
        session_id=session_id,
        api_origin=api_origin,
    )
    # If model is attached but viewer URL not yet set, provide the static viewer page
    if not preview_viewer_url and metadata.get("active_model_path"):
        preview_viewer_url = (
            f"{api_origin}/api/ui/viewer/{session_id}?session_id={session_id}&t=0"
        )

    family = (
        session_row.get("accepted_family")
        or metadata.get("proposed_family")
        or "unclassified"
    )
    confidence = metadata.get("family_confidence", "pending")
    evidence_text = (
        " | ".join(metadata.get("family_evidence", [])) or "No family evidence yet."
    )
    warning_text = (
        " | ".join(metadata.get("family_warnings", [])) or "No blocking warnings."
    )
    questions = metadata.get("clarifying_questions", [])
    question_text = (
        "\n".join(f"- {item}" for item in questions)
        if questions
        else "No outstanding clarification questions."
    )

    model_name = _sanitize_ui_text(
        metadata.get("model_name"),
        _resolve_model_name(),
    )
    model_provider = str(
        metadata.get("model_provider") or _provider_from_model_name(model_name)
    )
    model_profile = str(metadata.get("model_profile") or "balanced")
    workflow_mode = _normalize_workflow_mode(metadata.get("workflow_mode"))
    workflow_label, workflow_guidance_text, flow_header_text = _workflow_copy(
        workflow_mode,
        str(metadata.get("active_model_path") or ""),
    )
    local_endpoint = _sanitize_ui_text(
        metadata.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )
    readiness = _compute_readiness(metadata, db_ready=db_ready)

    return DashboardUIState(
        session_id=session_id,
        workflow_mode=workflow_mode,
        workflow_label=workflow_label,
        workflow_guidance_text=workflow_guidance_text,
        user_goal=session_row.get("user_goal") or DEFAULT_USER_GOAL,
        flow_header_text=flow_header_text,
        assumptions_text=_sanitize_ui_text(
            metadata.get("assumptions_text"),
            "Assume PETG, 0.4mm nozzle, 0.2mm layers, and 0.30mm mating clearance unless overridden.",
        ),
        active_model_path=str(metadata.get("active_model_path") or ""),
        active_model_status=str(
            metadata.get("active_model_status") or "No active model connected yet."
        ),
        active_model_type=str(metadata.get("active_model_type") or ""),
        active_model_configuration=str(
            metadata.get("active_model_configuration") or ""
        ),
        feature_target_text=str(metadata.get("feature_target_text") or ""),
        feature_target_status=str(
            metadata.get("feature_target_status")
            or "No grounded feature target selected."
        ),
        normalized_brief=(
            metadata.get("normalized_brief")
            or session_row.get("user_goal")
            or DEFAULT_USER_GOAL
        ),
        clarifying_questions_text=question_text,
        proposed_family=family,
        family_confidence=confidence,
        family_evidence_text=evidence_text,
        family_warning_text=warning_text,
        accepted_family=session_row.get("accepted_family") or "",
        checkpoints=checkpoints,
        checkpoints_text=checkpoints_text,
        evidence_rows=evidence_rows,
        evidence_rows_text=evidence_rows_text,
        structured_rendering_enabled=structured_rendering_enabled,
        manual_sync_ready=False,
        preview_url=preview_url,
        preview_status=preview_status,
        preview_orientation=metadata.get(
            "preview_orientation", DEFAULT_PREVIEW_ORIENTATION
        ),
        latest_message=metadata.get("latest_message", "Ready."),
        latest_tool=latest_tool,
        latest_error_text=str(metadata.get("latest_error_text") or ""),
        remediation_hint=str(metadata.get("remediation_hint") or ""),
        model_provider=model_provider,
        model_name=model_name,
        model_profile=model_profile,
        local_endpoint=local_endpoint,
        rag_source_path=str(metadata.get("rag_source_path") or ""),
        rag_namespace=str(metadata.get("rag_namespace") or "engineering-reference"),
        rag_status=str(
            metadata.get("rag_status") or "No retrieval source ingested yet."
        ),
        rag_index_path=str(metadata.get("rag_index_path") or ""),
        rag_chunk_count=int(metadata.get("rag_chunk_count") or 0),
        rag_provenance_text=str(
            metadata.get("rag_provenance_text")
            or "No retrieval provenance available yet."
        ),
        readiness_provider_configured=readiness["readiness_provider_configured"],
        readiness_adapter_mode=readiness["readiness_adapter_mode"],
        readiness_preview_ready=readiness["readiness_preview_ready"],
        readiness_db_ready=readiness["readiness_db_ready"],
        readiness_summary=readiness["readiness_summary"],
        context_used_pct=38,
        context_text="76k / 200k tokens",
        api_origin=api_origin,
        preview_viewer_url=preview_viewer_url,
        user_clarification_answer=str(metadata.get("user_clarification_answer") or ""),
        mocked_tools_text=(
            "MOCKED tools: " + ", ".join(metadata.get("mocked_tools", []))
            if metadata.get("mocked_tools")
            else ""
        ),
    ).model_dump()
