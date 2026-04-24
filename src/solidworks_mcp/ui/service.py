"""State and backend helpers for the Prefab CAD assistant dashboard.
"""

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
    from pydantic_ai.mcp import MCPServerStreamableHTTP
except ImportError:  # pragma: no cover
    Agent = None
    OpenAIChatModel = None
    OpenAIProvider = None
    MCPServerStreamableHTTP = None  # type: ignore[assignment,misc]

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
DEFAULT_CONTEXT_DIR = Path(".solidworks_mcp") / "ui_context"
DEFAULT_WORKFLOW_MODE = "unselected"
SUPPORTED_MODEL_UPLOAD_SUFFIXES = {".sldprt", ".sldasm", ".slddrw"}


class ClarificationResponse(BaseModel):
    """LLM response for goal clarification.
    
    Attributes:
        normalized_brief (str): The normalized brief value.
        questions (list[str]): The questions value.
    """

    normalized_brief: str = Field(min_length=10)
    questions: list[str] = Field(default_factory=list)


class CheckpointCandidate(BaseModel):
    """One suggested execution checkpoint.
    
    Attributes:
        allowed_tools (list[str]): The allowed tools value.
        rationale (str): The rationale value.
        title (str): The title value.
    """

    title: str = Field(min_length=3)
    allowed_tools: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=5)


class FamilyInspection(BaseModel):
    """LLM response for family classification.
    
    Attributes:
        checkpoints (list[CheckpointCandidate]): The checkpoints value.
        confidence (Literal["low", "medium", "high"]): The confidence value.
        evidence (list[str]): The evidence value.
        family (str): The family value.
        warnings (list[str]): The warnings value.
    """

    family: str = Field(min_length=3)
    confidence: Literal["low", "medium", "high"]
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checkpoints: list[CheckpointCandidate] = Field(default_factory=list)


class _HTMLTextExtractor(HTMLParser):
    """Build internal htmltext extractor.
    
    Attributes:
        _skip_depth (Any): The skip depth value.
    """

    def __init__(self) -> None:
        """Initialize the htmltext extractor.
        
        Returns:
            None: None.
        """

        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Provide handle starttag support for the htmltext extractor.
        
        Args:
            tag (str): The tag value.
            attrs (list[tuple[str, str | None]]): The attrs value.
        
        Returns:
            None: None.
        """

        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        """Provide handle endtag support for the htmltext extractor.
        
        Args:
            tag (str): The tag value.
        
        Returns:
            None: None.
        """

        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        """Provide handle data support for the htmltext extractor.
        
        Args:
            data (str): The data value.
        
        Returns:
            None: None.
        """

        if self._skip_depth == 0:
            normalized = " ".join(data.split())
            if normalized:
                self._parts.append(normalized)

    def text(self) -> str:
        """Provide text support for the htmltext extractor.
        
        Returns:
            str: The resulting text value.
        """

        return "\n".join(self._parts)


def ensure_preview_dir(preview_dir: Path | None = None) -> Path:
    """Create and return the preview image directory.
    
    Args:
        preview_dir (Path | None): The preview dir value. Defaults to None.
    
    Returns:
        Path: The result produced by the operation.
    """
    resolved = preview_dir or DEFAULT_PREVIEW_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def ensure_uploaded_model_dir(upload_dir: Path | None = None) -> Path:
    """Create and return the uploaded-model staging directory.
    
    Args:
        upload_dir (Path | None): The upload dir value. Defaults to None.
    
    Returns:
        Path: The result produced by the operation.
    """
    resolved = upload_dir or DEFAULT_UPLOADED_MODEL_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def ensure_context_dir(context_dir: Path | None = None) -> Path:
    """Create and return the dashboard context snapshot directory.
    
    Args:
        context_dir (Path | None): The context dir value. Defaults to None.
    
    Returns:
        Path: The result produced by the operation.
    """
    resolved = context_dir or DEFAULT_CONTEXT_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _parse_json_blob(payload: str | None) -> dict[str, Any]:
    """Build internal json blob.
    
    Args:
        payload (str | None): The payload value.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """

    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sanitize_ui_text(value: Any, fallback: str = "") -> str:
    """Build internal sanitize ui text.
    
    Args:
        value (Any): The value value.
        fallback (str): The fallback value. Defaults to "".
    
    Returns:
        str: The resulting text value.
    """

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


def _sanitize_model_path_text(value: Any) -> str:
    """Build internal sanitize model path text.
    
    Args:
        value (Any): The value value.
    
    Returns:
        str: The resulting text value.
    """

    text = _sanitize_ui_text(value, "")
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def _sanitize_preview_viewer_url(
    value: Any,
    *,
    session_id: str,
    api_origin: str,
) -> str:
    """Build internal sanitize preview viewer url.
    
    Args:
        value (Any): The value value.
        session_id (str): The session id value.
        api_origin (str): The api origin value.
    
    Returns:
        str: The resulting text value.
    """

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
        if parsed.netloc != expected.netloc:
            return ""
    return text


def _trace_json_default(value: Any) -> str:
    """Build internal trace json default.
    
    Args:
        value (Any): The value value.
    
    Returns:
        str: The resulting text value.
    """

    return str(value)


def _trace_json(value: Any) -> str:
    """Build internal trace json.
    
    Args:
        value (Any): The value value.
    
    Returns:
        str: The resulting text value.
    """

    return json.dumps(value, ensure_ascii=True, indent=2, default=_trace_json_default)


def _trace_session_row(session_row: dict[str, Any] | None) -> dict[str, Any]:
    """Build internal trace session row.
    
    Args:
        session_row (dict[str, Any] | None): The session row value.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """

    if not session_row:
        return {}
    return {key: value for key, value in session_row.items() if key != "metadata_json"}


def _trace_tool_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build internal trace tool records.
    
    Args:
        records (list[dict[str, Any]]): The records value.
    
    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """

    traced: list[dict[str, Any]] = []
    for record in records[-10:]:
        traced.append(
            {
                "id": record.get("id"),
                "tool_name": record.get("tool_name"),
                "success": record.get("success"),
                "input_json": record.get("input_json"),
                "output_json": record.get("output_json"),
                "created_at": record.get("created_at"),
            }
        )
    return traced


def _safe_context_name(context_name: str | None, session_id: str) -> str:
    """Build internal safe context name.
    
    Args:
        context_name (str | None): The context name value.
        session_id (str): The session id value.
    
    Returns:
        str: The resulting text value.
    """

    base = (context_name or session_id or "prefab-dashboard").strip()
    allowed = [ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in base]
    normalized = "".join(allowed).strip("-")
    return normalized or "prefab-dashboard"


def _context_file_path(
    session_id: str,
    *,
    context_name: str | None = None,
    context_dir: Path | None = None,
) -> Path:
    """Build internal context file path.
    
    Args:
        session_id (str): The session id value.
        context_name (str | None): The context name value. Defaults to None.
        context_dir (Path | None): The context dir value. Defaults to None.
    
    Returns:
        Path: The result produced by the operation.
    """

    target_dir = ensure_context_dir(context_dir)
    safe_name = _safe_context_name(context_name, session_id)
    return target_dir / f"{safe_name}.json"


def _filter_docs_text(raw_text: str, docs_query: str, *, max_chars: int = 2400) -> str:
    """Build internal filter docs text.
    
    Args:
        raw_text (str): The raw text value.
        docs_query (str): The docs query value.
        max_chars (int): The max chars value. Defaults to 2400.
    
    Returns:
        str: The resulting text value.
    """

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return "No docs content extracted from the endpoint response."

    query_tokens = [token for token in docs_query.lower().split() if token]
    if query_tokens:
        ranked = [
            line
            for line in lines
            if any(token in line.lower() for token in query_tokens)
        ]
        selected = ranked[:40] if ranked else lines[:40]
    else:
        selected = lines[:40]

    return "\n".join(selected)[:max_chars]


def _merge_metadata(
    session_id: str,
    *,
    db_path: Path | None = None,
    user_goal: str | None = None,
    **updates: Any,
) -> dict[str, Any]:
    """Build internal merge metadata.
    
    Args:
        session_id (str): The session id value.
        db_path (Path | None): The db path value. Defaults to None.
        user_goal (str | None): The user goal value. Defaults to None.
        **updates (Any): Additional keyword arguments forwarded to the call.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """

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


def _persist_ui_action(
    session_id: str,
    *,
    tool_name: str,
    db_path: Path | None = None,
    metadata_updates: dict[str, Any] | None = None,
    user_goal: str | None = None,
    input_payload: dict[str, Any] | None = None,
    output_payload: dict[str, Any] | None = None,
    output_metadata: bool = False,
    success: bool = True,
    checkpoint_id: int | None = None,
) -> dict[str, Any]:
    """Persist metadata updates and matching tool-call audit record in one place.
    
    Args:
        session_id (str): The session id value.
        tool_name (str): The tool name value.
        db_path (Path | None): The db path value. Defaults to None.
        metadata_updates (dict[str, Any] | None): The metadata updates value. Defaults to
                                                  None.
        user_goal (str | None): The user goal value. Defaults to None.
        input_payload (dict[str, Any] | None): The input payload value. Defaults to None.
        output_payload (dict[str, Any] | None): The output payload value. Defaults to None.
        output_metadata (bool): The output metadata value. Defaults to False.
        success (bool): The success value. Defaults to True.
        checkpoint_id (int | None): The checkpoint id value. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    merged_metadata: dict[str, Any] = {}
    if metadata_updates is not None or user_goal is not None:
        merged_metadata = _merge_metadata(
            session_id,
            db_path=db_path,
            user_goal=user_goal,
            **(metadata_updates or {}),
        )

    record_output = merged_metadata if output_metadata else output_payload

    insert_tool_call_record(
        session_id=session_id,
        checkpoint_id=checkpoint_id,
        tool_name=tool_name,
        input_json=(
            json.dumps(input_payload, ensure_ascii=True)
            if input_payload is not None
            else None
        ),
        output_json=(
            json.dumps(record_output, ensure_ascii=True)
            if record_output is not None
            else None
        ),
        success=success,
        db_path=db_path,
    )
    return merged_metadata


def _default_checkpoint_specs() -> list[dict[str, Any]]:
    """Build internal default checkpoint specs.
    
    Returns:
        list[dict[str, Any]]: A list containing the resulting items.
    """

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
    """Build internal provider from model name.
    
    Args:
        model_name (str): Embedding model name to use.
    
    Returns:
        str: The resulting text value.
    """

    if model_name.startswith("github:"):
        return "github"
    if model_name.startswith("openai:"):
        return "openai"
    if model_name.startswith("anthropic:"):
        return "anthropic"
    if model_name.startswith("local:"):
        return "local"
    return "custom"


def _normalize_model_name_for_provider(
    model_name: str | None,
    *,
    provider: str | None,
    profile: str | None = None,
) -> str:
    """Normalize free-form model names into provider-qualified routing strings.
    
    Args:
        model_name (str | None): Embedding model name to use.
        provider (str | None): The provider value.
        profile (str | None): The profile value. Defaults to None.
    
    Returns:
        str: The resulting text value.
    """
    normalized_provider = (provider or "github").strip().lower()
    normalized_profile = (profile or "balanced").strip().lower()
    raw_model = _sanitize_ui_text(model_name, "")

    if not raw_model:
        return _default_model_for_profile(normalized_provider, normalized_profile)

    # Already provider-qualified.
    if ":" in raw_model:
        return raw_model

    if normalized_provider == "local":
        return f"local:{raw_model}"
    if normalized_provider == "github":
        if "/" in raw_model:
            return f"github:{raw_model}"
        return f"github:openai/{raw_model}"
    if normalized_provider in {"openai", "anthropic"}:
        return f"{normalized_provider}:{raw_model}"

    return raw_model


def _default_model_for_profile(provider: str, profile: str) -> str:
    """Build internal default model for profile.
    
    Args:
        provider (str): The provider value.
        profile (str): The profile value.
    
    Returns:
        str: The resulting text value.
    """

    normalized_profile = (profile or "balanced").lower()
    if provider == "local":
        profile_models = {
            "small": "local:gemma4:e2b",
            "balanced": "local:gemma4:e4b",
            "large": "local:gemma4:26b",
        }
        return profile_models.get(normalized_profile, profile_models["balanced"])

    profile_models = {
        "small": "github:openai/gpt-4.1-mini",
        "balanced": "github:openai/gpt-4.1",
        "large": "github:openai/gpt-4.1",
    }
    return profile_models.get(normalized_profile, profile_models["balanced"])


def _feature_grounding_warning_text(
    *,
    active_model_path: str,
    feature_target_text: str,
    feature_tree_count: int,
) -> str:
    """Build internal feature grounding warning text.
    
    Args:
        active_model_path (str): The active model path value.
        feature_target_text (str): The feature target text value.
        feature_tree_count (int): The feature tree count value.
    
    Returns:
        str: The resulting text value.
    """

    if not active_model_path:
        return ""
    if not str(feature_target_text or "").strip():
        return ""
    if feature_tree_count > 0:
        return ""
    return (
        "Grounding is unavailable for the current attached model context because "
        "no feature tree rows were returned. Feature refs such as @Boss-Extrude1 "
        "cannot be resolved until the adapter can read the active model tree."
    )


def _provider_has_credentials(
    model_name: str, local_endpoint: str | None = None
) -> bool:
    """Build internal provider has credentials.
    
    Args:
        model_name (str): Embedding model name to use.
        local_endpoint (str | None): The local endpoint value. Defaults to None.
    
    Returns:
        bool: True if provider has credentials, otherwise False.
    """

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
    """Build internal normalize workflow mode.
    
    Args:
        workflow_mode (str | None): The workflow mode value.
    
    Returns:
        str: The resulting text value.
    """

    normalized = (workflow_mode or DEFAULT_WORKFLOW_MODE).strip().lower()
    if normalized in {"edit_existing", "new_design"}:
        return normalized
    return DEFAULT_WORKFLOW_MODE


def _workflow_copy(
    workflow_mode: str, active_model_path: str | None = None
) -> tuple[str, str, str]:
    """Build internal workflow copy.
    
    Args:
        workflow_mode (str): The workflow mode value.
        active_model_path (str | None): The active model path value. Defaults to None.
    
    Returns:
        tuple[str, str, str]: A tuple containing the resulting values.
    """

    has_active_model = bool(str(active_model_path or "").strip())
    if workflow_mode == "edit_existing":
        return (
            "Editing Existing Part or Assembly",
            "Attach an existing SolidWorks file, inspect the feature tree, then describe the feature edits you want.",
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
    """Build internal normalize feature targets.
    
    Args:
        feature_target_text (str | None): The feature target text value.
    
    Returns:
        list[str]: A list containing the resulting items.
    """

    targets: list[str] = []
    for raw in (feature_target_text or "").replace("\n", ",").split(","):
        normalized = raw.strip()
        if not normalized:
            continue
        candidate = normalized[1:] if normalized.startswith("@") else normalized
        if _looks_like_path_token(candidate):
            continue
        targets.append(candidate)
    return targets


def _looks_like_path_token(token: str) -> bool:
    """Build internal looks like path token.
    
    Args:
        token (str): The token value.
    
    Returns:
        bool: True if looks like path token, otherwise False.
    """

    normalized = token.strip()
    if not normalized:
        return False

    lowered = normalized.lower()
    if len(normalized) >= 2 and normalized[1] == ":" and normalized[0].isalpha():
        return True
    if "\\" in normalized or "/" in normalized:
        return True
    if lowered.endswith(
        (
            ".sldprt",
            ".sldasm",
            ".slddrw",
            ".step",
            ".stp",
            ".iges",
            ".igs",
            ".x_t",
            ".x_b",
        )
    ):
        return True
    return False


def _feature_target_status(
    features: list[dict[str, Any]], feature_target_text: str | None
) -> tuple[str, list[str], list[str]]:
    """Build internal feature target status.
    
    Args:
        features (list[dict[str, Any]]): The features value.
        feature_target_text (str | None): The feature target text value.
    
    Returns:
        tuple[str, list[str], list[str]]: A tuple containing the resulting values.
    """

    requested = _normalize_feature_targets(feature_target_text)
    if not requested:
        if str(feature_target_text or "").strip():
            return (
                "No valid feature targets found. Use feature names such as @Boss-Extrude1 or @Sketch2. File paths are ignored.",
                [],
                [],
            )
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
    """Build internal reference source.
    
    Args:
        source_path (Path): The source path value.
    
    Returns:
        str: The resulting text value.
    
    Raises:
        RuntimeError: Install pypdf to ingest PDF sources, or provide a text/markdown file
                      instead.
    """

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
    """Build internal is url reference.
    
    Args:
        source_path (str): The source path value.
    
    Returns:
        bool: True if url reference, otherwise False.
    """

    parsed = urlparse((source_path or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _read_reference_url(source_url: str) -> tuple[str, str]:
    """Build internal reference url.
    
    Args:
        source_url (str): The source url value.
    
    Returns:
        tuple[str, str]: A tuple containing the resulting values.
    
    Raises:
        RuntimeError: Install pypdf to ingest PDF sources, or provide a text, markdown, or
                      HTML source instead.
    """

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
    """Build internal agent model.
    
    Args:
        model_name (str): Embedding model name to use.
        local_endpoint (str | None): The local endpoint value. Defaults to None.
    
    Returns:
        Any: The result produced by the operation.
    
    Raises:
        RuntimeError: Pydantic-ai OpenAI provider support is not installed.
    """

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
    """Build internal materialize uploaded model.
    
    Args:
        session_id (str): The session id value.
        uploaded_files (list[dict[str, Any]] | None): The uploaded files value.
    
    Returns:
        Path: The result produced by the operation.
    
    Raises:
        RuntimeError: Uploaded model payload is not valid base64 data.
    """

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
    """Build internal compute readiness.
    
    Args:
        metadata (dict[str, Any]): The metadata value.
        db_ready (bool): The db ready value.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """

    provider = _sanitize_ui_text(
        metadata.get("model_provider"),
        "",
    ).lower()
    model_name = _normalize_model_name_for_provider(
        metadata.get("model_name"),
        provider=provider or None,
        profile=_sanitize_ui_text(metadata.get("model_profile"), "balanced"),
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
    """Build internal planned tools.
    
    Args:
        planned (dict[str, Any]): The planned value.
    
    Returns:
        list[str]: A list containing the resulting items.
    """

    tools = planned.get("tools", [])
    return [str(tool) for tool in tools] if isinstance(tools, list) else []


async def _run_checkpoint_tools(
    planned: dict[str, Any],
) -> dict[str, Any]:
    """Build internal run checkpoint tools.
    
    Unsupported tools are marked as MOCKED and returned in the summary.
    
    Args:
        planned (dict[str, Any]): The planned value.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
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
    user_goal: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Ensure one dashboard session row and default checkpoints exist.
    
    Args:
        session_id (str): The session id value. Defaults to DEFAULT_SESSION_ID.
        user_goal (str | None): The user goal value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    session_row = get_design_session(session_id, db_path=db_path)
    requested_goal = _sanitize_ui_text(user_goal, "") if user_goal is not None else ""
    if session_row is None:
        upsert_design_session(
            session_id=session_id,
            user_goal=requested_goal or DEFAULT_USER_GOAL,
            source_mode=DEFAULT_SOURCE_MODE,
            status="inspect",
            metadata_json=json.dumps(
                {
                    "normalized_brief": requested_goal or DEFAULT_USER_GOAL,
                    "preview_orientation": DEFAULT_PREVIEW_ORIENTATION,
                },
                ensure_ascii=True,
            ),
            db_path=db_path,
        )
    elif requested_goal and requested_goal != session_row["user_goal"]:
        upsert_design_session(
            session_id=session_id,
            user_goal=requested_goal,
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
    """Persist the accepted goal for the active dashboard session.
    
    Args:
        session_id (str): The session id value.
        user_goal (str): The user goal value.
        db_path (Path | None): The db path value. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    ensure_dashboard_session(session_id, user_goal=user_goal, db_path=db_path)
    _persist_ui_action(
        session_id,
        tool_name="ui.approve_brief",
        db_path=db_path,
        user_goal=user_goal,
        metadata_updates={
            "normalized_brief": user_goal,
            "latest_message": "Brief accepted.",
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"user_goal": user_goal},
        output_metadata=True,
    )
    return build_dashboard_state(session_id, db_path=db_path)


def accept_family_choice(
    session_id: str,
    family: str | None = None,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Accept the proposed family and advance the session.
    
    Args:
        session_id (str): The session id value.
        family (str | None): The family value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
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
    _persist_ui_action(
        session_id,
        tool_name="ui.accept_family",
        db_path=db_path,
        metadata_updates={
            "accepted_family": accepted_family,
            "latest_message": f"Family accepted: {accepted_family}.",
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"family": accepted_family},
    )
    return build_dashboard_state(session_id, db_path=db_path)


async def execute_next_checkpoint(
    session_id: str,
    *,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Handle execute next checkpoint.
    
    Args:
        session_id (str): The session id value.
        db_path (Path | None): The db path value. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
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
    """Compare the latest two snapshots and summarize the reconciliation step.
    
    Args:
        session_id (str): The session id value.
        db_path (Path | None): The db path value. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
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

    _persist_ui_action(
        session_id,
        tool_name="ui.reconcile_manual_edits",
        db_path=db_path,
        metadata_updates={"latest_message": message},
        output_payload={"message": message},
    )
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
    """Persist editable assumptions and model/provider preferences.
    
    Args:
        session_id (str): The session id value.
        assumptions_text (str | None): The assumptions text value. Defaults to None.
        model_provider (str | None): The model provider value. Defaults to None.
        model_profile (str | None): The model profile value. Defaults to None.
        model_name (str | None): Embedding model name to use. Defaults to None.
        local_endpoint (str | None): The local endpoint value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    ensure_dashboard_session(session_id, db_path=db_path)
    provider = (model_provider or "github").strip().lower()
    profile = (model_profile or "balanced").strip().lower()
    resolved_model = _normalize_model_name_for_provider(
        model_name,
        provider=provider,
        profile=profile,
    )
    resolved_endpoint = _sanitize_ui_text(
        local_endpoint,
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )
    _persist_ui_action(
        session_id,
        tool_name="ui.update_preferences",
        db_path=db_path,
        metadata_updates={
            "assumptions_text": _sanitize_ui_text(
                assumptions_text,
                "No assumptions provided yet.",
            ),
            "model_provider": provider,
            "model_profile": profile,
            "model_name": resolved_model,
            "local_endpoint": resolved_endpoint,
            "latest_message": "Updated assumptions and model preferences.",
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={
            "assumptions_text": assumptions_text,
            "model_provider": provider,
            "model_profile": profile,
            "model_name": resolved_model,
            "local_endpoint": resolved_endpoint,
        },
        output_metadata=True,
    )
    return build_dashboard_state(session_id, db_path=db_path)


def select_workflow_mode(
    session_id: str,
    *,
    workflow_mode: str,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Persist the onboarding workflow branch for the active dashboard session.
    
    Args:
        session_id (str): The session id value.
        workflow_mode (str): The workflow mode value.
        db_path (Path | None): The db path value. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    normalized_mode = _normalize_workflow_mode(workflow_mode)
    workflow_label, workflow_guidance, _ = _workflow_copy(normalized_mode)
    if normalized_mode == "new_design":
        metadata = _parse_json_blob(session_row.get("metadata_json"))
        metadata.update(
            {
                "workflow_mode": normalized_mode,
                "active_model_path": "",
                "active_model_status": "No active model connected yet.",
                "active_model_type": "",
                "active_model_configuration": "",
                "feature_target_text": "",
                "feature_target_status": "No grounded feature target selected.",
                "selected_feature_name": "",
                "selected_feature_selector_name": "",
                "preview_viewer_url": "",
                "preview_view_urls": {},
                "preview_status": "No preview captured yet.",
                "preview_stl_ready": False,
                "preview_png_ready": False,
                "clarifying_questions": [],
                "user_clarification_answer": "",
                "proposed_family": "unclassified",
                "family_confidence": "pending",
                "family_evidence": [],
                "family_warnings": [],
                "mocked_tools": [],
                "rag_source_path": "",
                "rag_status": "No retrieval source ingested yet.",
                "rag_index_path": "",
                "rag_chunk_count": 0,
                "rag_provenance_text": "No retrieval provenance available yet.",
                "docs_context_text": "No docs context loaded yet.",
                "notes_text": "",
                "orchestration_status": "Ready.",
                "context_save_status": "",
                "context_load_status": "",
                "latest_message": f"Workflow selected: {workflow_label}.",
                "latest_error_text": "",
                "remediation_hint": "",
            }
        )

        # Use a fresh starter prompt for new-part design work instead of
        # carrying forward edit-existing goals from the previous run.
        starter_goal = "Describe the new part you want to design."
        metadata["normalized_brief"] = starter_goal

        upsert_design_session(
            session_id=session_id,
            user_goal=starter_goal,
            source_mode=session_row.get("source_mode") or DEFAULT_SOURCE_MODE,
            accepted_family=None,
            status="inspect",
            current_checkpoint_index=0,
            metadata_json=json.dumps(metadata, ensure_ascii=True),
            db_path=db_path,
        )

        # Reset queue state so "Execute Next Checkpoint" starts clean.
        for row in list_plan_checkpoints(session_id, db_path=db_path):
            update_plan_checkpoint(
                int(row.get("id") or 0),
                approved_by_user=False,
                executed=False,
                result_json="",
                db_path=db_path,
            )
    else:
        metadata = _merge_metadata(
            session_id,
            db_path=db_path,
            workflow_mode=normalized_mode,
            latest_message=f"Workflow selected: {workflow_label}.",
            latest_error_text="",
            remediation_hint="",
        )
    _persist_ui_action(
        session_id,
        tool_name="ui.select_workflow_mode",
        db_path=db_path,
        input_payload={"workflow_mode": normalized_mode},
        output_payload={
            "workflow_mode": normalized_mode,
            "workflow_label": workflow_label,
            "workflow_guidance_text": workflow_guidance,
            "metadata": metadata,
        },
    )
    return build_dashboard_state(session_id, db_path=db_path)


async def run_go_orchestration(
    session_id: str,
    *,
    user_goal: str,
    assumptions_text: str | None = None,
    user_answer: str = "",
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Run a single end-to-end pass that updates inputs, review, and output lanes.
    
    Args:
        session_id (str): The session id value.
        user_goal (str): The user goal value.
        assumptions_text (str | None): The assumptions text value. Defaults to None.
        user_answer (str): The user answer value. Defaults to "".
        db_path (Path | None): The db path value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    try:
        goal_text = _sanitize_ui_text(user_goal, DEFAULT_USER_GOAL)
        approve_design_brief(session_id, goal_text, db_path=db_path)

        session_row = get_design_session(session_id, db_path=db_path) or {}
        metadata = _parse_json_blob(session_row.get("metadata_json"))
        update_ui_preferences(
            session_id,
            assumptions_text=assumptions_text,
            model_provider=str(metadata.get("model_provider") or "github"),
            model_profile=str(metadata.get("model_profile") or "balanced"),
            model_name=metadata.get("model_name"),
            local_endpoint=metadata.get("local_endpoint"),
            db_path=db_path,
        )

        await request_clarifications(
            session_id,
            goal_text,
            user_answer=user_answer,
            db_path=db_path,
        )
        await inspect_family(session_id, goal_text, db_path=db_path)

        _persist_ui_action(
            session_id,
            tool_name="ui.orchestrate_go",
            db_path=db_path,
            metadata_updates={
                "orchestration_status": "Go run completed: inputs saved, clarifications refreshed, engineering review updated.",
                "latest_message": "Go run completed across workflow, review, and model output lanes.",
                "latest_error_text": "",
                "remediation_hint": "",
            },
            input_payload={
                "user_goal": goal_text,
                "assumptions_text": assumptions_text,
                "user_answer": user_answer,
            },
            output_payload={
                "status": "success",
                "message": "Go orchestration completed.",
            },
        )
    except Exception as exc:
        logger.exception("[ui.run_go_orchestration] failed session_id={}", session_id)
        _merge_metadata(
            session_id,
            db_path=db_path,
            orchestration_status="Go run failed.",
            latest_error_text=str(exc),
            remediation_hint="Review provider credentials/model selection and retry Go.",
        )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def update_session_notes(
    session_id: str,
    *,
    notes_text: str,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Persist free-form engineering notes in session metadata.
    
    Args:
        session_id (str): The session id value.
        notes_text (str): The notes text value.
        db_path (Path | None): The db path value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    _persist_ui_action(
        session_id,
        tool_name="ui.notes.update",
        db_path=db_path,
        metadata_updates={
            "notes_text": notes_text,
            "latest_message": "Notes saved.",
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"notes_text": notes_text},
    )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def fetch_docs_context(
    session_id: str,
    *,
    docs_query: str = "",
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Fetch docs text from the docs endpoint and store a filtered context snippet.
    
    Args:
        session_id (str): The session id value.
        docs_query (str): The docs query value. Defaults to "".
        db_path (Path | None): The db path value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    docs_url = f"{api_origin}/docs"
    query_text = _sanitize_ui_text(docs_query, "solidworks workflow")
    try:
        request = Request(
            docs_url,
            headers={"User-Agent": "solidworks-mcp-ui/1.0"},
        )
        with urlopen(request, timeout=8) as response:
            html = response.read().decode("utf-8", errors="ignore")
        extractor = _HTMLTextExtractor()
        extractor.feed(html)
        snippet = _filter_docs_text(extractor.text(), query_text)
        _persist_ui_action(
            session_id,
            tool_name="ui.docs.fetch",
            db_path=db_path,
            metadata_updates={
                "docs_query": query_text,
                "docs_context_text": snippet,
                "latest_message": "Docs context updated from MCP docs endpoint.",
                "latest_error_text": "",
                "remediation_hint": "",
            },
            input_payload={"query": query_text, "url": docs_url},
            output_payload={"chars": len(snippet)},
        )
    except Exception as exc:
        logger.exception("[ui.fetch_docs_context] failed session_id={}", session_id)
        _merge_metadata(
            session_id,
            db_path=db_path,
            docs_query=query_text,
            docs_context_text="",
            latest_error_text=str(exc),
            remediation_hint="Verify the /docs endpoint is reachable, then retry docs refresh.",
        )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def save_session_context(
    session_id: str,
    *,
    context_name: str | None = None,
    db_path: Path | None = None,
    context_dir: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Persist the current dashboard state to a plain JSON file and metadata.
    
    Args:
        session_id (str): The session id value.
        context_name (str | None): The context name value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.
        context_dir (Path | None): The context dir value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    state = build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)
    target_path = _context_file_path(
        session_id,
        context_name=context_name,
        context_dir=context_dir,
    )
    payload = {
        "session_id": session_id,
        "saved_at": int(time.time()),
        "state": state,
    }
    target_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    message = f"Context saved to {target_path}."
    _persist_ui_action(
        session_id,
        tool_name="ui.context.save",
        db_path=db_path,
        metadata_updates={
            "context_save_status": message,
            "context_name_input": _safe_context_name(context_name, session_id),
            "context_file_input": str(target_path),
            "last_context_file": str(target_path),
            "latest_message": message,
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"context_name": context_name},
        output_payload={"path": str(target_path)},
    )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def load_session_context(
    session_id: str,
    *,
    context_file: str | None = None,
    db_path: Path | None = None,
    context_dir: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Load a previously saved plain-file context snapshot back into session metadata.
    
    Args:
        session_id (str): The session id value.
        context_file (str | None): The context file value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.
        context_dir (Path | None): The context dir value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    context_file_text = _sanitize_ui_text(context_file, "")
    source_path = (
        Path(context_file_text)
        if context_file_text
        else _context_file_path(session_id, context_dir=context_dir)
    )
    if not source_path.exists():
        message = f"Context load failed. File not found: {source_path}."
        _merge_metadata(
            session_id,
            db_path=db_path,
            context_load_status=message,
            context_file_input=str(source_path),
            latest_error_text=message,
            remediation_hint="Save context first or provide a valid context file path.",
        )
        return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)

    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        message = f"Context load failed: {exc}."
        _merge_metadata(
            session_id,
            db_path=db_path,
            context_load_status=message,
            context_file_input=str(source_path),
            latest_error_text=message,
            remediation_hint="Ensure the context file is valid JSON saved by this dashboard.",
        )
        return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)

    loaded_state = payload.get("state") if isinstance(payload, dict) else {}
    if not isinstance(loaded_state, dict):
        loaded_state = {}

    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    for key in [
        "workflow_mode",
        "assumptions_text",
        "active_model_path",
        "active_model_status",
        "feature_target_text",
        "feature_target_status",
        "normalized_brief",
        "user_clarification_answer",
        "model_provider",
        "model_profile",
        "model_name",
        "local_endpoint",
        "rag_source_path",
        "rag_namespace",
        "notes_text",
        "docs_query",
        "docs_context_text",
    ]:
        if key in loaded_state:
            metadata[key] = loaded_state.get(key)

    upsert_design_session(
        session_id=session_id,
        user_goal=_sanitize_ui_text(
            loaded_state.get("user_goal"),
            session_row.get("user_goal") or DEFAULT_USER_GOAL,
        ),
        source_mode=session_row.get("source_mode") or DEFAULT_SOURCE_MODE,
        accepted_family=(
            _sanitize_ui_text(loaded_state.get("accepted_family"), "")
            or session_row.get("accepted_family")
        ),
        status=session_row.get("status") or "active",
        current_checkpoint_index=session_row.get("current_checkpoint_index") or 0,
        metadata_json=json.dumps(metadata, ensure_ascii=True),
        db_path=db_path,
    )

    message = f"Context loaded from {source_path}."
    _persist_ui_action(
        session_id,
        tool_name="ui.context.load",
        db_path=db_path,
        metadata_updates={
            "context_load_status": message,
            "context_name_input": _safe_context_name(source_path.stem, session_id),
            "context_file_input": str(source_path),
            "last_context_file": str(source_path),
            "latest_message": message,
            "latest_error_text": "",
            "remediation_hint": "",
        },
        input_payload={"context_file": str(source_path)},
    )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


async def open_target_model(
    session_id: str,
    *,
    model_path: str | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    feature_target_text: str | None = None,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Open a target model in SolidWorks and persist session state before connect/preview.
    
    Args:
        session_id (str): The session id value.
        model_path (str | None): The model path value. Defaults to None.
        uploaded_files (list[dict[str, Any]] | None): The uploaded files value. Defaults to
                                                      None.
        feature_target_text (str | None): The feature target text value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    
    Raises:
        RuntimeError: If the operation cannot be completed.
    """
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
        normalized_model_path = _sanitize_model_path_text(model_path)
        if not normalized_model_path:
            _merge_metadata(
                session_id,
                db_path=db_path,
                latest_message="No target model was provided.",
                latest_error_text="Missing model path or uploaded model file.",
                remediation_hint="Choose a local SolidWorks file or provide an absolute model path.",
                feature_target_text=feature_target_text or "",
                workflow_mode="edit_existing",
            )
            return build_dashboard_state(
                session_id, db_path=db_path, api_origin=api_origin
            )
        resolved_path = Path(normalized_model_path).expanduser()
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
    tool_input = {
        "model_path": str(resolved_path.resolve()),
        "uploaded_file_name": uploaded_files[0].get("name") if uploaded_files else None,
        "feature_target_text": feature_target_text or "",
    }
    try:
        await adapter.connect()
        logger.info(
            "[ui.open_target_model] opening model path={} ",
            str(resolved_path.resolve()),
        )
        open_result = await adapter.open_model(str(resolved_path.resolve()))
        if not open_result.is_success:
            raise RuntimeError(open_result.error or "Failed to open target model.")

        if hasattr(adapter, "get_model_info"):
            info_result = await adapter.get_model_info()
            if info_result.is_success and isinstance(info_result.data, dict):
                model_info = info_result.data

        metadata = _merge_metadata(
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
        _merge_metadata(
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
    """Open a target model, inspect its feature tree, and persist grounded context.
    
    Args:
        session_id (str): The session id value.
        model_path (str | None): The model path value. Defaults to None.
        uploaded_files (list[dict[str, Any]] | None): The uploaded files value. Defaults to
                                                      None.
        feature_target_text (str | None): The feature target text value. Defaults to None.
        db_path (Path | None): The db path value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    
    Raises:
        RuntimeError: If the operation cannot be completed.
    """
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
        normalized_model_path = _sanitize_model_path_text(model_path)
        if not normalized_model_path:
            _merge_metadata(
                session_id,
                db_path=db_path,
                latest_message="No target model was provided.",
                latest_error_text="Missing model path or uploaded model file.",
                remediation_hint="Choose a local SolidWorks file or provide an absolute model path.",
                feature_target_text=feature_target_text or "",
                workflow_mode="edit_existing",
            )
            return build_dashboard_state(
                session_id, db_path=db_path, api_origin=api_origin
            )
        resolved_path = Path(normalized_model_path).expanduser()
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
    attach_succeeded = False
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
        _merge_metadata(
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
            # After the model is attached and persisted, generate the 3D viewer and
            # screenshots in one refresh pass so the response represents the final UI state.
            # Reuse the adapter that already opened the requested model so the first
            # capture pass is guaranteed to target that document.
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


def ingest_reference_source(
    session_id: str,
    *,
    source_path: str,
    namespace: str,
    chunk_size: int = 1200,
    overlap: int = 200,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Ingest a user-provided local file or URL into a simple local retrieval index.
    
    Args:
        session_id (str): The session id value.
        source_path (str): The source path value.
        namespace (str): Namespace used to isolate stored data.
        chunk_size (int): Maximum number of characters to keep in each chunk. Defaults to
                          1200.
        overlap (int): Number of overlapping characters between chunks. Defaults to 200.
        db_path (Path | None): The db path value. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
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

        # --- FAISS vector index (best-effort; skipped if faiss/sentence-transformers
        # are not installed) ---------------------------------------------------
        try:
            from ..agents.vector_rag import VectorRAGIndex  # noqa: PLC0415

            idx = VectorRAGIndex.load(
                namespace=resolved_namespace, rag_dir=DEFAULT_RAG_DIR
            )
            for chunk in payload["chunks"]:
                idx.ingest_text(
                    chunk["text"],
                    source=source_identifier,
                    tags=[resolved_namespace],
                )
            idx.save()
            logger.info(
                "[ui.ingest_reference_source] FAISS index updated namespace={} chunks={}",
                resolved_namespace,
                len(chunks),
            )
        except ImportError:
            logger.debug(
                "[ui.ingest_reference_source] FAISS not available; skipping vector index"
            )
        except Exception as faiss_exc:
            logger.warning(
                "[ui.ingest_reference_source] FAISS indexing failed (non-fatal): {}",
                faiss_exc,
            )
        # -----------------------------------------------------------------------
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
    """Build internal resolve model name.
    
    Args:
        explicit_model (str | None): The explicit model value. Defaults to None.
    
    Returns:
        str: The resulting text value.
    """

    return explicit_model or os.getenv("SOLIDWORKS_UI_MODEL", "github:openai/gpt-4.1")


def _ensure_provider_credentials(
    model_name: str, local_endpoint: str | None = None
) -> None:
    """Build internal provider credentials.
    
    Args:
        model_name (str): Embedding model name to use.
        local_endpoint (str | None): The local endpoint value. Defaults to None.
    
    Returns:
        None: None.
    
    Raises:
        RuntimeError: Set SOLIDWORKS_UI_LOCAL_ENDPOINT before using local model routing.
    """

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
    """Build internal run structured agent.
    
    Args:
        system_prompt (str): The system prompt value.
        user_prompt (str): The user prompt value.
        result_type (type[BaseModel]): The result type value.
        model_name (str | None): Embedding model name to use. Defaults to None.
        local_endpoint (str | None): The local endpoint value. Defaults to None.
    
    Returns:
        BaseModel | RecoverableFailure: The result produced by the operation.
    """

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
    # --- Prompt construction ---
    # Wrap the caller-supplied prompts in clearly labelled sections so that both
    # the model and any future reader can see exactly what is being submitted.
    mcp_tool_catalog = (
        "## SOLIDWORKS MCP TOOL CATALOG\n"
        "Use these tool names in checkpoint plans and rationale fields:\n"
        "  open_model, get_model_info, list_features(include_suppressed), get_mass_properties,\n"
        "  classify_feature_tree, create_sketch, add_line, add_arc, add_circle, add_rectangle,\n"
        "  create_extrusion, create_revolve, create_cut, export_image, export_step, export_stl,\n"
        "  select_feature, check_interference [mocked until wired], analyze_geometry,\n"
        "  generate_vba_code, execute_macro\n"
        "Prefer tools in the order listed above (inspect → classify → plan → execute → verify).\n"
        "Do not invent tools not in this list."
    )
    enriched_system_prompt = (
        "## ROLE AND ORCHESTRATION AGENTS\n"
        f"{system_prompt}\n\n"
        "## AVAILABLE ORCHESTRATION AGENTS\n"
        "  - Feature-Tree Reconstruction agent: inspect → classify → delegate; safe checkpoint plans.\n"
        "  - Printer-Profile Tolerancing agent: converts printer/material inputs to explicit tolerance "
        "ranges per feature type (press-fit, sliding, snap, hinge, clip).\n"
        "  - SolidWorks Research Validator: validates material, clearance, and build-volume facts.\n\n"
        "## GUARDRAILS\n"
        "  - Use the SolidWorks MCP tool surface for actionable plans.\n"
        "  - Do not invent unavailable tools; prefer known MCP tool names.\n"
        "  - If confidence is low or the model is unavailable, propose inspection steps first.\n"
        "  - For sheet metal or advanced solid families, route to VBA-aware planning.\n"
        "  - Always include explicit tolerance/clearance values when manufacturing context is present."
    )
    enriched_user_prompt = f"## PLANNING REQUEST\n{user_prompt}\n\n{mcp_tool_catalog}"

    # --- MCP server toolset wiring ---
    # When SOLIDWORKS_MCP_URL is set (or defaulting to the standard local port),
    # connect pydantic-ai to the real running MCP server so the agent can call
    # tools directly rather than only referencing them by name in text.
    mcp_server_url = os.getenv("SOLIDWORKS_MCP_URL", "http://127.0.0.1:8000/")
    mcp_agent_tools = os.getenv("SOLIDWORKS_MCP_AGENT_TOOLS", "auto").lower()
    toolsets: list[Any] = []
    if mcp_agent_tools != "off" and MCPServerStreamableHTTP is not None:
        toolsets = [
            MCPServerStreamableHTTP(
                mcp_server_url,
                tool_prefix="sw",
                include_instructions=True,
            )
        ]

    _ensure_provider_credentials(resolved_model, resolved_endpoint)
    try:
        configured_model = _build_agent_model(
            resolved_model,
            resolved_endpoint,
        )
        agent = Agent(
            configured_model,
            system_prompt=enriched_system_prompt,
            output_type=[result_type, RecoverableFailure],
            toolsets=toolsets if toolsets else None,
        )
        if toolsets:
            try:
                async with agent:
                    result = await agent.run(enriched_user_prompt)
            except Exception:
                # MCP server not reachable — fall back to planning-only mode (no live tools)
                logger.debug(
                    "MCP server at %s unreachable; falling back to planning-only agent run.",
                    mcp_server_url,
                )
                agent_fallback = Agent(
                    configured_model,
                    system_prompt=enriched_system_prompt,
                    output_type=[result_type, RecoverableFailure],
                )
                result = await agent_fallback.run(enriched_user_prompt)
        else:
            result = await agent.run(enriched_user_prompt)
    except Exception as exc:
        return RecoverableFailure(
            explanation=f"Model routing failed: {exc}",
            remediation_steps=[
                "Open Model Controls and run Auto-Detect Local Model, or switch provider/model to a supported value.",
            ],
            retry_focus="Use a provider-qualified model name, then retry this action.",
            should_retry=True,
        )
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
    """Generate focused follow-up questions for the current design goal using LLM.
    
    Calls GitHub Copilot (openai/gpt-4.1) by default or a model specified in
    SOLIDWORKS_UI_MODEL env. Requires GH_TOKEN or GITHUB_API_KEY with models:read scope.
    
    Args:
        session_id (str): The session id value.
        user_goal (str): The user goal value.
        user_answer (str): The user answer value. Defaults to "".
        db_path (Path | None): The db path value. Defaults to None.
        model_name (str | None): Embedding model name to use. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    ensure_dashboard_session(session_id, user_goal=user_goal, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    resolved_model_name = _normalize_model_name_for_provider(
        model_name or metadata.get("model_name"),
        provider=_sanitize_ui_text(metadata.get("model_provider"), "github"),
        profile=_sanitize_ui_text(metadata.get("model_profile"), "balanced"),
    )
    resolved_local_endpoint = _sanitize_ui_text(
        metadata.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )
    # --- Prompt: structured sections so the model sees clearly labelled inputs ---
    answer_section = (
        f"\n## USER ANSWERS / CLARIFICATIONS\n{user_answer}" if user_answer else ""
    )
    assumptions_text = _sanitize_ui_text(
        metadata.get("assumptions_text"), "<none specified>"
    )
    prompt = (
        "## TASK\n"
        "Prepare a SolidWorks design brief using the Printer-Profile-Tolerancing skill.\n"
        "Return a normalized_brief and at most three clarifying_questions that unblock the next modeling step.\n\n"
        "## DESIGN GOAL\n"
        f"{user_goal}\n\n"
        "## MANUFACTURING ASSUMPTIONS\n"
        f"{assumptions_text}\n\n"
        "## MODEL CONTEXT\n"
        f"Active model path : {metadata.get('active_model_path', '') or '<none>'}\n"
        f"Feature target refs: {metadata.get('feature_target_text', '') or '<none>'}\n"
        f"Reference corpus   : {metadata.get('rag_provenance_text', '') or '<none>'}"
        f"{answer_section}\n\n"
        "## OUTPUT CONTRACT\n"
        "normalized_brief: concise paragraph with explicit dimensions/tolerances where known (≥10 chars).\n"
        "questions       : list of up to 3 highest-leverage questions that unblock modeling.\n"
        "  - Include material/layer-height/nozzle values if missing from assumptions.\n"
        "  - Include critical fit/clearance targets if unspecified.\n"
        "  - Do not ask questions already answered above."
    )
    # LLM Call: request_clarifications — routes to configured provider (GitHub or local)
    result = await _run_structured_agent(
        system_prompt=(
            "## ROLE\n"
            "You are a CAD planning assistant applying the Printer-Profile-Tolerancing skill.\n"
            "Normalize goals into manufacturing-ready language with explicit tolerance/clearance "
            "targets (e.g. '0.30 mm mating clearance', '0.2 mm layer height'). "
            "Ask only the highest-leverage questions that unblock the SolidWorks modeling steps. "
            "Always surface material, nozzle size, and orientation constraints when present in the goal."
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
    """Run LLM-backed family classification and suggested checkpoints.
    
    Calls GitHub Copilot to infer the likely SolidWorks feature family (e.g., "bracket",
    "housing", "fastener", "assembly") and suggests 4 conservative checkpoints with allowed
    MCP tools.
    
    Args:
        session_id (str): The session id value.
        user_goal (str): The user goal value.
        db_path (Path | None): The db path value. Defaults to None.
        model_name (str | None): Embedding model name to use. Defaults to None.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    ensure_dashboard_session(session_id, user_goal=user_goal, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    resolved_model_name = _normalize_model_name_for_provider(
        model_name or metadata.get("model_name"),
        provider=_sanitize_ui_text(metadata.get("model_provider"), "github"),
        profile=_sanitize_ui_text(metadata.get("model_profile"), "balanced"),
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
    # Rebuild as clearly demarcated prompt with skill context embedded
    local_family = metadata.get("proposed_family", "") or "<not yet classified>"
    local_evidence = " | ".join(metadata.get("family_evidence", [])) or "<none>"
    prompt = (
        "## TASK\n"
        "Apply the Feature-Tree-Reconstruction skill to classify the SolidWorks feature family "
        "and produce a human-reviewable checkpoint plan.\n\n"
        "## DESIGN GOAL\n"
        f"{user_goal}\n\n"
        "## MODEL CONTEXT\n"
        f"Active model path  : {metadata.get('active_model_path', '') or '<none>'}\n"
        f"Active model status: {metadata.get('active_model_status', '') or '<none>'}\n"
        f"Feature target refs: {metadata.get('feature_target_text', '') or '<none>'}\n"
        f"Feature target status: {metadata.get('feature_target_status', '') or '<none>'}\n\n"
        "## LOCAL CLASSIFIER EVIDENCE (pre-computed)\n"
        f"Family  : {local_family}\n"
        f"Evidence: {local_evidence}\n\n"
        "## REFERENCE CORPUS\n"
        f"{metadata.get('rag_provenance_text', '') or '<none>'}\n\n"
        "## FEATURE-TREE RECONSTRUCTION SKILL\n"
        "Inspection sequence when model is available (use your mcp tools):\n"
        "  open_model → get_model_info → list_features(include_suppressed=True) "
        "→ get_mass_properties → classify_feature_tree\n"
        "Feature families: revolve | extrude | sheet_metal | advanced_solid | assembly | drawing | unknown\n"
        "Delegation rules:\n"
        "  - sheet_metal or advanced_solid → VBA-aware reconstruction path\n"
        "  - simple part family → direct MCP checkpoint plan\n"
        "  - assembly → component-first decomposition, part-level plan per component\n"
        "Guardrail: never reconstruct from silhouette only. "
        "If confidence is low and contradictory evidence exists, propose more inspection steps.\n\n"
        "## OUTPUT CONTRACT\n"
        "Return: family, confidence (high/medium/low), evidence[], warnings[], checkpoints[3-6].\n"
        "Each checkpoint: title, allowed_tools[] (from MCP tool catalog), rationale."
    )
    # LLM Call: inspect_family — Feature-Tree-Reconstruction agent route
    result = await _run_structured_agent(
        system_prompt=(
            "## ROLE\n"
            "You are a SolidWorks routing assistant applying the Feature-Tree-Reconstruction skill.\n"
            "Classify the feature family with evidence and confidence, then produce a safe "
            "checkpoint plan for human review.\n\n"
            "## ORCHESTRATION NOTES\n"
            "  - Inspection before planning: never produce a build plan without at least one "
            "evidence item from model inspection or user-confirmed context.\n"
            "  - Propose 3-6 conservative checkpoints. Require human confirmation before each "
            "irreversible step.\n"
            "  - For sheet metal or unsupported advanced features, route to VBA-aware planning.\n"
            "  - Surface warnings when evidence is contradictory or confidence is low."
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
    """Build internal public preview url.
    
    Args:
        preview_path (Path): The preview path value.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        str: The resulting text value.
    """

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
    adapter_override: Any | None = None,
    active_model_path_override: str | None = None,
    reopen_active_model: bool = True,
) -> dict[str, Any]:
    """Export the current SolidWorks viewport to a PNG preview and STL for the 3D viewer.
    
    Uses export_image(view_orientation=...) from the active adapter. Supports orientations:
    "front", "top", "right", "isometric", "current". Also exports an STL file to power the
    embedded Three.js viewer.
    
    Args:
        session_id (str): The session id value.
        orientation (str): The orientation value. Defaults to DEFAULT_PREVIEW_ORIENTATION.
        db_path (Path | None): The db path value. Defaults to None.
        preview_dir (Path | None): The preview dir value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
        adapter_override (Any | None): The adapter override value. Defaults to None.
        active_model_path_override (str | None): The active model path override value.
                                                 Defaults to None.
        reopen_active_model (bool): The reopen active model value. Defaults to True.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
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
    active_model_path = active_model_path_override or metadata.get("active_model_path")
    adapter = adapter_override
    owns_adapter = adapter_override is None

    try:
        if adapter is None:
            config = load_config()
            adapter = await create_adapter(config)
        if owns_adapter:
            await adapter.connect()
        if reopen_active_model and active_model_path and hasattr(adapter, "open_model"):
            candidate_path = Path(str(active_model_path))
            if candidate_path.exists():
                logger.info(
                    "[ui.refresh_preview] reopening active model {}",
                    str(candidate_path.resolve()),
                )
                await adapter.open_model(str(candidate_path.resolve()))
        # ------------------------------------------------------------------ #
        # Step 1: Export 3D model for the interactive Three.js viewer.
        # Try GLB first (preserves assembly colors + named mesh hierarchy);
        # fall back to merged STL if GLB is unsupported or fails.
        # ------------------------------------------------------------------ #
        glb_path = resolved_preview_dir / f"{session_id}.glb"
        stl_path = resolved_preview_dir / f"{session_id}.stl"
        viewer_ts = int(time.time())
        viewer_format = "none"  # "glb" | "stl" | "none"
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
            # GLB unavailable — try STL (merged single mesh)
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

        # The viewer URL always points to the iframe; cache-bust with timestamp so
        # the browser re-fetches the model when it changes.  Pass the format so
        # the viewer JS knows which Three.js loader to instantiate.
        preview_viewer_url = (
            f"{api_origin}/api/ui/viewer/{session_id}?t={viewer_ts}&fmt={viewer_format}"
        )

        # ------------------------------------------------------------------ #
        # Step 2: Export PNG screenshot (optional — best-effort)
        # ------------------------------------------------------------------ #
        png_payload = {
            "file_path": str(preview_path.resolve()),
            "format_type": "png",
            "width": 1280,
            "height": 720,
            "view_orientation": orientation,
        }
        png_ok = False
        png_error: str = ""
        snapshot_id: str | None = None
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

        # ------------------------------------------------------------------ #
        # Step 3: Export per-orientation PNG thumbnails for the multi-pane view
        # ------------------------------------------------------------------ #
        VIEW_ORIENTATIONS = ["isometric", "front", "top", "right"]
        preview_view_urls: dict[str, str] = {}
        try:
            config2 = load_config()
            adapter2 = await create_adapter(config2)
            await adapter2.connect()
            if active_model_path and hasattr(adapter2, "open_model"):
                candidate_path = Path(str(active_model_path))
                if candidate_path.exists():
                    await adapter2.open_model(str(candidate_path.resolve()))
            # Re-select the previously selected feature so its SolidWorks
            # highlight glow is visible in the orientation screenshots.
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
                        # Some view operations can drop selection; re-apply before each capture.
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
                            "[ui.refresh_preview] view PNG {} exported",
                            view_name,
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

        # Do not clear existing view URLs when a refresh attempt returns no images.
        # Keep prior captures to avoid UI flicker or apparent state reset.
        existing_view_urls = metadata.get("preview_view_urls")
        if isinstance(existing_view_urls, dict):
            if not preview_view_urls:
                preview_view_urls = dict(existing_view_urls)
            else:
                merged_view_urls = dict(existing_view_urls)
                merged_view_urls.update(preview_view_urls)
                preview_view_urls = merged_view_urls

        # Compose status message
        viewer_label = (
            f"3D viewer ({viewer_format.upper()})"
            if viewer_format != "none"
            else "3D viewer (no model)"
        )
        png_label = "PNG" if png_ok else f"no PNG ({png_error})"
        status_msg = f"Preview refreshed ({viewer_label}, {png_label})."

        _merge_metadata(
            session_id,
            db_path=db_path,
            preview_orientation=orientation,
            latest_message=status_msg,
            preview_status=status_msg,
            latest_snapshot_id=snapshot_id,
            preview_viewer_url=preview_viewer_url,
            preview_stl_ready=(viewer_format != "none"),
            preview_png_ready=png_ok,
            preview_view_urls=preview_view_urls,
            latest_error_text="",
            remediation_hint="",
        )
    except Exception as exc:
        logger.exception("[ui.refresh_preview] failed: {}", exc)
        # Preserve whatever viewer URL was already set so the 3D view doesn't vanish
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
    
    Uses SelectByID2 via the pywin32 adapter.  In mock mode the selection is acknowledged
    without a COM side-effect.  Returns the full dashboard state so the UI can hydrate
    cleanly.
    
    Args:
        session_id (str): The session id value.
        feature_name (str): The feature name value.
        db_path (Path | None): The db path value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    ensure_dashboard_session(session_id, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    active_model_path = metadata.get("active_model_path")
    resolved_name = (feature_name or "").strip()
    if not resolved_name:
        _merge_metadata(
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
        _merge_metadata(
            session_id,
            db_path=db_path,
            selected_feature_name=resolved_name,
            selected_feature_selector_name=selected_name,
            latest_message=(
                f"Selected '{resolved_name}' ({entity_type}) in SolidWorks."
                if selected
                else (
                    f"Tracking '{resolved_name}' from the feature tree. SolidWorks did not expose a direct selectable handle for that row."
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
        _merge_metadata(
            session_id,
            db_path=db_path,
            latest_error_text=str(exc),
            remediation_hint="Ensure SolidWorks is open with the target model loaded.",
        )
    return build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)


def build_dashboard_state(
    session_id: str = DEFAULT_SESSION_ID,
    *,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Assemble the dashboard payload consumed by the Prefab UI.
    
    Args:
        session_id (str): The session id value. Defaults to DEFAULT_SESSION_ID.
        db_path (Path | None): The db path value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """
    session_row = ensure_dashboard_session(session_id, db_path=db_path)
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    db_ready = bool(session_row)
    workflow_mode = _normalize_workflow_mode(metadata.get("workflow_mode"))
    active_model_path = _sanitize_model_path_text(metadata.get("active_model_path"))
    is_new_design_clean = workflow_mode == "new_design" and not active_model_path

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

        if is_new_design_clean and not row["executed"]:
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
    if not is_new_design_clean:
        all_evidence = list_evidence_links(session_id, db_path=db_path)
        model_scoped_sources = {"active_model", "feature_target"}

        filtered_evidence: list[dict[str, Any]] = []
        for evidence in all_evidence:
            source_type = str(evidence.get("source_type") or "")
            source_id = str(evidence.get("source_id") or "")
            if (
                source_type in model_scoped_sources
                and active_model_path
                and source_id
                and source_id != active_model_path
            ):
                # Keep the table anchored to the currently attached model.
                continue
            filtered_evidence.append(evidence)

        # For feature-target grounding, show only the latest result so the
        # table reflects the current target text instead of historical misses.
        latest_feature_target: dict[str, Any] | None = None
        compact_evidence: list[dict[str, Any]] = []
        for evidence in filtered_evidence:
            if str(evidence.get("source_type") or "") == "feature_target":
                latest_feature_target = evidence
                continue
            compact_evidence.append(evidence)
        if latest_feature_target is not None:
            compact_evidence.append(latest_feature_target)

        for evidence in compact_evidence[-6:]:
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
    tool_history_text = _trace_json(_trace_tool_records(tool_history[-20:]))

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

    # Feature tree: read from the most-recent snapshot that contains feature data.
    _META_NAMES = {
        "sensors",
        "annotations",
        "history",
        "design binder",
        "solid bodies",
        "surface bodies",
        "lights, cameras and scene",
        "equations",
        "favorites",
        "selection sets",
        "3d views",
    }
    _META_TYPES = {
        "sensorfolder",
        "annotationfolder",
        "historyfolder",
        "designbinder",
        "solidbodyfolder",
        "surfacebodyfolder",
        "lightsfolder",
        "mategroup",
    }
    feature_tree_items: list[dict[str, Any]] = []
    if not is_new_design_clean:
        for snap in snapshots:
            raw_tree = snap.get("feature_tree_json")
            if raw_tree:
                try:
                    parsed = json.loads(raw_tree)
                    if isinstance(parsed, list):
                        feature_tree_items = [
                            f
                            for f in parsed
                            if f.get("name", "").lower() not in _META_NAMES
                            and f.get("type", "").lower() not in _META_TYPES
                        ]
                        break
                except Exception:
                    pass

    # Mark the selected feature for UI row highlighting
    _selected_name = str(metadata.get("selected_feature_name") or "").strip()
    if _selected_name:
        feature_tree_items = [
            {**f, "_selected": "●" if f.get("name") == _selected_name else ""}
            for f in feature_tree_items
        ]

    # 3D viewer URL: read from metadata (set when model connects or preview refreshes)
    preview_viewer_url = _sanitize_preview_viewer_url(
        metadata.get("preview_viewer_url"),
        session_id=session_id,
        api_origin=api_origin,
    )
    # Only expose interactive viewer URL when STL generation has succeeded.
    if (
        not preview_viewer_url
        and bool(metadata.get("preview_stl_ready"))
        and metadata.get("active_model_path")
    ):
        preview_viewer_url = (
            f"{api_origin}/api/ui/viewer/{session_id}?session_id={session_id}&t=0"
        )

    preview_status = _sanitize_ui_text(
        metadata.get("preview_status"),
        preview_status,
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
    active_model_status = _sanitize_ui_text(metadata.get("active_model_status"), "")
    if active_model_path and not active_model_status:
        active_model_status = (
            f"Model path set: {Path(active_model_path).name} (connect pending)."
        )
    if not active_model_path and not active_model_status:
        active_model_status = "No active model connected yet."

    workflow_label, workflow_guidance_text, flow_header_text = _workflow_copy(
        workflow_mode,
        active_model_path,
    )
    local_endpoint = _sanitize_ui_text(
        metadata.get("local_endpoint"),
        os.getenv("SOLIDWORKS_UI_LOCAL_ENDPOINT", "http://127.0.0.1:11434/v1"),
    )
    readiness = _compute_readiness(metadata, db_ready=db_ready)

    active_model_name = Path(active_model_path).name if active_model_path else "<none>"
    selected_feature_name = str(metadata.get("selected_feature_name") or "")
    preview_views = metadata.get("preview_view_urls") or {}
    model_context_lines = [
        f"Model file: {active_model_name}",
        f"Absolute path: {active_model_path or '<none>'}",
        f"Model type: {str(metadata.get('active_model_type') or '<unknown>')}",
        f"Configuration: {str(metadata.get('active_model_configuration') or '<unknown>')}",
        f"Feature tree rows: {len(feature_tree_items)}",
        f"Selected feature: {selected_feature_name or '<none>'}",
        f"Feature targets: {str(metadata.get('feature_target_text') or '<none>')}",
        f"Preview views captured: {', '.join(sorted(preview_views.keys())) or '<none>'}",
        f"Latest preview status: {preview_status}",
    ]
    model_context_text = "\n".join(model_context_lines)
    context_summary = (
        f"{active_model_name} | {str(metadata.get('active_model_type') or 'unknown')}"
        f" | config {str(metadata.get('active_model_configuration') or '<unknown>')}"
        f" | features {len(feature_tree_items)}"
    )
    feature_grounding_warning_text = _feature_grounding_warning_text(
        active_model_path=active_model_path,
        feature_target_text=str(metadata.get("feature_target_text") or ""),
        feature_tree_count=len(feature_tree_items),
    )
    canonical_prompt_text = "\n".join(
        [
            f"Goal: {session_row.get('user_goal') or DEFAULT_USER_GOAL}",
            f"Assumptions: {_sanitize_ui_text(metadata.get('assumptions_text'), '') or '<none>'}",
            f"Active model path: {active_model_path or '<none>'}",
            f"Active model status: {active_model_status}",
            f"Feature targets: {str(metadata.get('feature_target_text') or '<none>')}",
            f"Feature target status: {str(metadata.get('feature_target_status') or '<none>')}",
            f"Accepted/proposed family: {session_row.get('accepted_family') or metadata.get('proposed_family') or '<none>'}",
            f"RAG provenance: {str(metadata.get('rag_provenance_text') or '<none>')}",
            f"Docs context: {str(metadata.get('docs_context_text') or '<none>')}",
            f"Engineering notes: {str(metadata.get('notes_text') or '<none>')}",
        ]
    )

    state = DashboardUIState(
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
        active_model_path=active_model_path,
        active_model_status=active_model_status,
        active_model_type=str(metadata.get("active_model_type") or ""),
        active_model_configuration=str(
            metadata.get("active_model_configuration") or ""
        ),
        feature_target_text=str(metadata.get("feature_target_text") or ""),
        feature_target_status=str(
            metadata.get("feature_target_status")
            or "No grounded feature target selected."
        ),
        feature_grounding_warning_text=feature_grounding_warning_text,
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
        local_model_status_text=str(
            metadata.get("local_model_status_text") or "Local model controls idle."
        ),
        local_model_busy=bool(metadata.get("local_model_busy") or False),
        local_model_available=bool(metadata.get("local_model_available") or False),
        local_model_recommended_tier=str(
            metadata.get("local_model_recommended_tier") or ""
        ),
        local_model_recommended_ollama_model=str(
            metadata.get("local_model_recommended_ollama_model") or ""
        ),
        local_model_pull_command=str(metadata.get("local_model_pull_command") or ""),
        local_model_label=str(metadata.get("local_model_label") or ""),
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
        docs_query=str(metadata.get("docs_query") or "SolidWorks MCP endpoints"),
        docs_context_text=str(
            metadata.get("docs_context_text") or "No docs context loaded yet."
        ),
        notes_text=str(metadata.get("notes_text") or ""),
        orchestration_status=str(metadata.get("orchestration_status") or "Ready."),
        context_save_status=str(metadata.get("context_save_status") or ""),
        context_load_status=str(metadata.get("context_load_status") or ""),
        context_name_input=str(metadata.get("context_name_input") or session_id),
        context_file_input=str(metadata.get("last_context_file") or ""),
        readiness_provider_configured=readiness["readiness_provider_configured"],
        readiness_adapter_mode=readiness["readiness_adapter_mode"],
        readiness_preview_ready=readiness["readiness_preview_ready"],
        readiness_db_ready=readiness["readiness_db_ready"],
        readiness_summary=readiness["readiness_summary"],
        context_used_pct=38,
        context_text=context_summary,
        model_context_text=model_context_text,
        canonical_prompt_text=canonical_prompt_text,
        tool_history_text=tool_history_text,
        api_origin=api_origin,
        preview_viewer_url=preview_viewer_url,
        preview_view_urls=metadata.get("preview_view_urls") or {},
        user_clarification_answer=str(metadata.get("user_clarification_answer") or ""),
        mocked_tools_text=(
            "MOCKED tools: " + ", ".join(metadata.get("mocked_tools", []))
            if metadata.get("mocked_tools")
            else ""
        ),
        feature_tree_items=feature_tree_items,
        selected_feature_name=str(metadata.get("selected_feature_name") or ""),
    ).model_dump()
    logger.debug(
        "[ui.trace.state] session_id={} model_path={} selected={} feature_rows={} preview_views={} latest_tool={}",
        session_id,
        state.get("active_model_path") or "<none>",
        state.get("selected_feature_name") or "<none>",
        len(state.get("feature_tree_items") or []),
        list((state.get("preview_view_urls") or {}).keys()),
        state.get("latest_tool") or "waiting",
    )
    return state


def build_dashboard_trace_payload(
    session_id: str = DEFAULT_SESSION_ID,
    *,
    db_path: Path | None = None,
    api_origin: str = DEFAULT_API_ORIGIN,
) -> dict[str, Any]:
    """Build the dashboard trace payload.
    
    Args:
        session_id (str): The session id value. Defaults to DEFAULT_SESSION_ID.
        db_path (Path | None): The db path value. Defaults to None.
        api_origin (str): The api origin value. Defaults to DEFAULT_API_ORIGIN.
    
    Returns:
        dict[str, Any]: A dictionary containing the resulting values.
    """

    ensure_dashboard_session(session_id, db_path=db_path)
    session_row = get_design_session(session_id, db_path=db_path) or {}
    metadata = _parse_json_blob(session_row.get("metadata_json"))
    state = build_dashboard_state(session_id, db_path=db_path, api_origin=api_origin)
    tool_records = _trace_tool_records(
        list_tool_call_records(session_id, db_path=db_path)
    )
    session_row_payload = _trace_session_row(session_row)

    payload = {
        "session_id": session_id,
        "workflow_mode": state.get("workflow_mode", "unselected"),
        "latest_message": state.get("latest_message", "Ready."),
        "latest_error_text": state.get("latest_error_text", ""),
        "debug_summary": (
            f"workflow={state.get('workflow_mode', 'unselected')}"
            f" | model_path={state.get('active_model_path', '') or '<none>'}"
            f" | latest_tool={state.get('latest_tool', 'waiting')}"
            f" | tool_records={len(tool_records)}"
        ),
        "session_row": session_row_payload,
        "session_row_text": _trace_json(session_row_payload),
        "metadata": metadata,
        "metadata_text": _trace_json(metadata),
        "state": state,
        "state_text": _trace_json(state),
        "tool_records": tool_records,
        "tool_records_text": _trace_json(tool_records),
    }
    logger.debug(
        "[ui.trace.snapshot] session_id={} model_path={} selected={} tool_records={} preview_views={}",
        session_id,
        state.get("active_model_path") or "<none>",
        state.get("selected_feature_name") or "<none>",
        len(tool_records),
        list((state.get("preview_view_urls") or {}).keys()),
    )
    return payload
