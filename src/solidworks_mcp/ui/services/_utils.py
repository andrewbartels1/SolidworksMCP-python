"""Shared utility functions for the Prefab CAD assistant dashboard services.

This module provides pure utility functions with no service-level dependencies.
All functions are stateless and accept their inputs as arguments.

Design principles applied:
- Single Responsibility: each function does exactly one thing.
- No side effects: these helpers never write to the database directly.
- No circular imports: this module is the lowest layer; it imports only from
  the database and schema layers, never from sibling service modules.
"""

from __future__ import annotations

import json
import os
import base64
import binascii
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from html.parser import HTMLParser
from io import BytesIO
from importlib import import_module
from urllib.request import Request, urlopen
from loguru import logger

from ...agents.history_db import (
    get_design_session,
    insert_tool_call_record,
    upsert_design_session,
)

# ---------------------------------------------------------------------------
# Module-level defaults (mirrored from the top-level service constants so
# that utility helpers can be used in isolation during testing).
# ---------------------------------------------------------------------------
DEFAULT_SESSION_ID = "prefab-dashboard"
DEFAULT_USER_GOAL = (
    "Design a printable mounting component with documented constraints and fastener strategy."
)
DEFAULT_SOURCE_MODE = "prompt"
DEFAULT_API_ORIGIN = os.getenv("SOLIDWORKS_UI_API_ORIGIN", "http://127.0.0.1:8766")
DEFAULT_PREVIEW_ORIENTATION = "current"
DEFAULT_WORKFLOW_MODE = "unselected"
# Default RAG index directory
DEFAULT_RAG_DIR = Path(".solidworks_mcp") / "rag"
SUPPORTED_MODEL_UPLOAD_SUFFIXES = frozenset({".sldprt", ".sldasm", ".slddrw"})


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def parse_json_blob(payload: str | None) -> dict[str, Any]:
    """Parse a JSON string into a dict, returning an empty dict on any failure.

    Args:
        payload: Raw JSON string, or ``None``.

    Returns:
        Parsed dict, or ``{}`` if parsing fails.
    """
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def sanitize_ui_text(value: Any, fallback: str = "") -> str:
    """Return a clean string from *value*, using *fallback* for empty/invalid inputs.

    Strips template placeholders such as ``{{ field }}``, bare quotes, and
    pydantic-ai expression strings that sometimes leak into UI state.

    Args:
        value: Arbitrary input (str, None, etc.).
        fallback: Value to return when *value* is empty or invalid.

    Returns:
        Cleaned string, or *fallback*.
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


def sanitize_model_path_text(value: Any) -> str:
    """Strip surrounding quotes from a model path string.

    Args:
        value: Raw model path value from UI state.

    Returns:
        Cleaned path string, or ``""`` if empty.
    """
    text = sanitize_ui_text(value, "")
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def sanitize_preview_viewer_url(
    value: Any,
    *,
    session_id: str,
    api_origin: str,
) -> str:
    """Validate and return a preview viewer URL, or ``""`` if it looks wrong.

    Rejects URLs pointing at unexpected origins or session IDs to prevent
    open-redirect-style issues in the embedded viewer iframe.

    Args:
        value: Raw URL string from session metadata.
        session_id: Expected session ID segment in the path.
        api_origin: Allowed API origin (scheme + host + port).

    Returns:
        Validated URL string, or ``""`` if validation fails.
    """
    text = sanitize_ui_text(value, "")
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


# ---------------------------------------------------------------------------
# Trace / debug helpers
# ---------------------------------------------------------------------------


def _trace_json_default(value: Any) -> str:
    """JSON serialisation default: convert unknown types to their str repr."""
    return str(value)


def trace_json(value: Any) -> str:
    """Serialise *value* to a pretty-printed JSON string for operator trace panels.

    Args:
        value: Any JSON-serialisable value.

    Returns:
        Indented JSON string.
    """
    return json.dumps(value, ensure_ascii=True, indent=2, default=_trace_json_default)


def trace_session_row(session_row: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of *session_row* with the bulky ``metadata_json`` field removed.

    Args:
        session_row: Raw session row dict from the database.

    Returns:
        Filtered dict suitable for debug display.
    """
    if not session_row:
        return {}
    return {key: value for key, value in session_row.items() if key != "metadata_json"}


def trace_tool_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the last ten tool-call records as lean trace dicts.

    Args:
        records: Full list of tool-call records for the session.

    Returns:
        Trimmed list of trace-friendly dicts (id, tool_name, success, …).
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


# ---------------------------------------------------------------------------
# Context / file path helpers
# ---------------------------------------------------------------------------


def safe_context_name(context_name: str | None, session_id: str) -> str:
    """Normalise a context name to a safe filesystem slug.

    Args:
        context_name: User-supplied context name, may be None.
        session_id: Fallback identifier.

    Returns:
        Alphanumeric + hyphen slug, never empty.
    """
    base = (context_name or session_id or "prefab-dashboard").strip()
    allowed = [ch if (ch.isalnum() or ch in {"-", "_"}) else "-" for ch in base]
    normalized = "".join(allowed).strip("-")
    return normalized or "prefab-dashboard"


# ---------------------------------------------------------------------------
# Session metadata merge / persist helpers
# ---------------------------------------------------------------------------


def merge_metadata(
    session_id: str,
    *,
    db_path: Path | None = None,
    user_goal: str | None = None,
    **updates: Any,
) -> dict[str, Any]:
    """Read session metadata, merge *updates* into it, and write it back.

    Implements the optimistic read-modify-write pattern used across all
    service functions that need to update one or more metadata keys without
    overwriting unrelated keys.

    Args:
        session_id: Target session identifier.
        db_path: Optional override for the SQLite database path.
        user_goal: When provided, also updates the ``user_goal`` column.
        **updates: Arbitrary key-value pairs to merge into metadata.

    Returns:
        The merged metadata dict after the write.
    """
    session_row = get_design_session(session_id, db_path=db_path)
    metadata = parse_json_blob(session_row["metadata_json"]) if session_row else {}
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


def persist_ui_action(
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
    """Persist metadata updates and a matching tool-call audit record atomically.

    Combines :func:`merge_metadata` and ``insert_tool_call_record`` so callers
    can update session state and write an audit entry in a single call.

    Args:
        session_id: Target session identifier.
        tool_name: Logical name for the audit record (e.g. ``"ui.approve_brief"``).
        db_path: Optional override for the SQLite database path.
        metadata_updates: Key-value pairs to merge into session metadata.
        user_goal: When provided, also updates the ``user_goal`` column.
        input_payload: Dict serialised as the ``input_json`` audit column.
        output_payload: Dict serialised as the ``output_json`` audit column.
        output_metadata: When ``True``, write the merged metadata as ``output_json``.
        success: Whether the action succeeded.
        checkpoint_id: Optional FK to the associated plan checkpoint.

    Returns:
        The merged metadata dict after the write.
    """
    merged_metadata: dict[str, Any] = {}
    if metadata_updates is not None or user_goal is not None:
        merged_metadata = merge_metadata(
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


# ---------------------------------------------------------------------------
# Workflow copy strings
# ---------------------------------------------------------------------------


def normalize_workflow_mode(workflow_mode: str | None) -> str:
    """Normalise a raw workflow mode string to a known value.

    Args:
        workflow_mode: Raw mode string from UI state.

    Returns:
        ``"edit_existing"``, ``"new_design"``, or ``DEFAULT_WORKFLOW_MODE``.
    """
    normalized = (workflow_mode or DEFAULT_WORKFLOW_MODE).strip().lower()
    if normalized in {"edit_existing", "new_design"}:
        return normalized
    return DEFAULT_WORKFLOW_MODE


def workflow_copy(
    workflow_mode: str, active_model_path: str | None = None
) -> tuple[str, str, str]:
    """Return display copy for the workflow selector.

    Args:
        workflow_mode: Normalised workflow mode string.
        active_model_path: Currently attached model path, if any.

    Returns:
        Three-tuple of (label, guidance_text, flow_header_text).
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


# ---------------------------------------------------------------------------
# Model name / provider helpers
# ---------------------------------------------------------------------------


def provider_from_model_name(model_name: str) -> str:
    """Infer the provider prefix from a provider-qualified model name.

    Args:
        model_name: Model name such as ``"github:openai/gpt-4.1"``.

    Returns:
        Provider string: ``"github"``, ``"openai"``, ``"anthropic"``,
        ``"local"``, or ``"custom"``.
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


def default_model_for_profile(provider: str, profile: str) -> str:
    """Return the default model name for the given provider and profile tier.

    Args:
        provider: Provider string (``"github"``, ``"local"``, etc.).
        profile: Profile tier (``"small"``, ``"balanced"``, ``"large"``).

    Returns:
        Provider-qualified model name string.
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


def normalize_model_name_for_provider(
    model_name: str | None,
    *,
    provider: str | None,
    profile: str | None = None,
) -> str:
    """Normalise a free-form model name into a provider-qualified routing string.

    Args:
        model_name: Raw model name from UI state, may be None or unqualified.
        provider: Explicit provider override (``"github"``, ``"local"``, etc.).
        profile: Profile tier used as fallback when *model_name* is empty.

    Returns:
        Provider-qualified model name (e.g. ``"github:openai/gpt-4.1"``).
    """
    normalized_provider = (provider or "github").strip().lower()
    normalized_profile = (profile or "balanced").strip().lower()
    raw_model = sanitize_ui_text(model_name, "")

    if not raw_model:
        return default_model_for_profile(normalized_provider, normalized_profile)

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


def provider_has_credentials(
    model_name: str, local_endpoint: str | None = None
) -> bool:
    """Check whether the required credentials exist for the given model.

    Args:
        model_name: Provider-qualified model name.
        local_endpoint: Local API endpoint URL (required for ``"local:"`` models).

    Returns:
        ``True`` if the relevant API key / endpoint is configured.
    """
    provider = provider_from_model_name(model_name)
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


# ---------------------------------------------------------------------------
# Feature-tree helpers
# ---------------------------------------------------------------------------


def normalize_feature_targets(feature_target_text: str | None) -> list[str]:
    """Parse a comma- or newline-separated feature target string into a list.

    Strips ``@`` prefixes and filters out tokens that look like file paths.

    Args:
        feature_target_text: Raw input such as ``"@Boss-Extrude1, @Sketch2"``.

    Returns:
        List of normalised feature name strings.
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
    """Return ``True`` if *token* looks like a filesystem path rather than a feature name."""
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


def feature_target_status(
    features: list[dict[str, Any]], feature_target_text: str | None
) -> tuple[str, list[str], list[str]]:
    """Compute matched / missing feature target status.

    Args:
        features: Feature tree rows from the active snapshot.
        feature_target_text: Raw feature target input from the UI.

    Returns:
        Three-tuple of (status_message, matched_names, missing_names).
    """
    requested = normalize_feature_targets(feature_target_text)
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


def feature_grounding_warning_text(
    *,
    active_model_path: str,
    feature_target_text: str,
    feature_tree_count: int,
) -> str:
    """Return a warning string when feature grounding cannot proceed.

    Args:
        active_model_path: Currently attached model path.
        feature_target_text: Raw feature target refs from UI.
        feature_tree_count: Number of rows in the current feature tree snapshot.

    Returns:
        Warning message, or ``""`` if grounding is possible.
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


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

_DEFAULT_PREVIEW_DIR = Path(".solidworks_mcp") / "ui_previews"
_DEFAULT_UPLOADED_MODEL_DIR = Path(".solidworks_mcp") / "ui_uploads"
_DEFAULT_CONTEXT_DIR = Path(".solidworks_mcp") / "ui_context"


def ensure_preview_dir(preview_dir: Path | None = None) -> Path:
    """Create and return the preview image directory.

    Args:
        preview_dir: Override directory; defaults to ``.solidworks_mcp/ui_previews``.

    Returns:
        Resolved ``Path`` that is guaranteed to exist.
    """
    resolved = preview_dir or _DEFAULT_PREVIEW_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def ensure_uploaded_model_dir(upload_dir: Path | None = None) -> Path:
    """Create and return the uploaded-model staging directory.

    Args:
        upload_dir: Override directory; defaults to ``.solidworks_mcp/ui_uploads``.

    Returns:
        Resolved ``Path`` that is guaranteed to exist.
    """
    resolved = upload_dir or _DEFAULT_UPLOADED_MODEL_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def ensure_context_dir(context_dir: Path | None = None) -> Path:
    """Create and return the dashboard context snapshot directory.

    Args:
        context_dir: Override directory; defaults to ``.solidworks_mcp/ui_context``.

    Returns:
        Resolved ``Path`` that is guaranteed to exist.
    """
    resolved = context_dir or _DEFAULT_CONTEXT_DIR
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def context_file_path(
    session_id: str,
    *,
    context_name: str | None = None,
    context_dir: Path | None = None,
) -> Path:
    """Return the canonical path for a context snapshot JSON file.

    Args:
        session_id: Session identifier used as the default filename.
        context_name: Optional override name (will be slugified).
        context_dir: Override directory for context files.

    Returns:
        ``Path`` pointing at ``<context_dir>/<safe_name>.json``.
    """
    target_dir = ensure_context_dir(context_dir)
    safe_name = safe_context_name(context_name, session_id)
    return target_dir / f"{safe_name}.json"


# ---------------------------------------------------------------------------
# HTML text extractor (shared by docs fetching and URL reference reading)
# ---------------------------------------------------------------------------


class HTMLTextExtractor(HTMLParser):
    """Minimal HTML-to-plain-text extractor.

    Strips tags and collects visible text content. Script, style, and nav
    elements are suppressed entirely.
    """

    _SKIP_TAGS = frozenset({"script", "style", "nav", "footer", "head"})

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:  # type: ignore[override]
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def text(self) -> str:
        """Return the accumulated plain text.

        Returns:
            Plain text content extracted from the HTML document.
        """
        return "\n".join(self._parts)


# ---------------------------------------------------------------------------
# Docs / reference helpers
# ---------------------------------------------------------------------------


def filter_docs_text(text: str, query: str, *, max_chars: int = 4000) -> str:
    """Filter plain-text docs content to lines most relevant to *query*.

    Returns up to ``max_chars`` characters of the most relevant lines, scored
    by how many query tokens they contain.

    Args:
        text: Full plain-text docs content.
        query: Space-separated keyword query.
        max_chars: Maximum characters to return.

    Returns:
        Filtered and truncated text snippet.
    """
    if not text:
        return ""
    tokens = {t.lower() for t in query.split() if t}
    lines = text.splitlines()
    scored: list[tuple[int, str]] = []
    for line in lines:
        lower = line.lower()
        score = sum(1 for t in tokens if t in lower)
        if score > 0:
            scored.append((score, line))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [line for _, line in scored]
    combined = "\n".join(selected)
    return combined[:max_chars]


def is_url_reference(source_path: str) -> bool:
    """Return ``True`` when *source_path* is an http/https URL.

    Args:
        source_path: Raw source path string from the UI.

    Returns:
        ``True`` if the path starts with http:// or https://.
    """
    parsed = urlparse((source_path or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def read_reference_source(source_path: Path) -> str:
    """Read the text content of a local file (PDF, markdown, text).

    PDF extraction requires the optional ``pypdf`` package.

    Args:
        source_path: Local file path to read.

    Returns:
        Extracted plain text content.

    Raises:
        RuntimeError: When a PDF is supplied but ``pypdf`` is not installed.
    """
    try:
        PdfReader = import_module("pypdf").PdfReader
    except ImportError:
        PdfReader = None

    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        if PdfReader is None:
            raise RuntimeError(
                "Install pypdf to ingest PDF sources, or provide a text/markdown file instead."
            )
        reader = PdfReader(str(source_path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()

    return source_path.read_text(encoding="utf-8")


def read_reference_url(source_url: str) -> tuple[str, str]:
    """Fetch content from a URL and return (text, label).

    Handles HTML (stripped), PDF (requires ``pypdf``), and plain text.

    Args:
        source_url: http/https URL to fetch.

    Returns:
        Tuple of (plain_text_content, label) where label is derived from the URL path.

    Raises:
        RuntimeError: When a PDF is served but ``pypdf`` is not installed.
    """
    try:
        PdfReader = import_module("pypdf").PdfReader
    except ImportError:
        PdfReader = None

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
        parser = HTMLTextExtractor()
        parser.feed(decoded)
        return parser.text().strip(), label

    return decoded.strip(), label


# ---------------------------------------------------------------------------
# Model upload helper
# ---------------------------------------------------------------------------


def materialize_uploaded_model(
    session_id: str,
    uploaded_files: list[dict[str, Any]] | None,
    *,
    upload_dir: Path | None = None,
) -> Path:
    """Decode a base64-encoded uploaded model file and write it to the staging directory.

    Args:
        session_id: Dashboard session identifier used as a staging subdirectory.
        uploaded_files: List of file payload dicts, each with ``name`` and ``data`` fields.
        upload_dir: Override for the upload staging directory.

    Returns:
        Path pointing at the decoded file on disk.

    Raises:
        RuntimeError: When no file is provided, the name is missing, the suffix is
            unsupported, or the data field is not valid base64.
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

    target_dir = ensure_uploaded_model_dir(upload_dir) / session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_name
    target_path.write_bytes(file_bytes)
    return target_path
