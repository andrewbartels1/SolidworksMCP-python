"""Classify tool failures into actionable error categories.

The MCP tool error boundary (``tool_boundary``) asks this module what kind of
failure it is looking at, so the payload can carry an ``error_type`` and a
``hint`` telling the caller what to do next instead of an opaque message.

Adapter errors usually arrive as *strings* - ``_handle_com_operation`` flattens
COM exceptions to ``"COM error in <op>: (<hresult>, '<text>', ...)"`` - so every
rule can match on the message text, and COM rules also on the HRESULT taken
from either a ``com_error`` exception or that text.

Rules are evaluated in order; the first match wins. Add a category by
appending a rule - callers never change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# HRESULTs (signed 32-bit, as pywin32 reports them).
RPC_E_DISCONNECTED = -2147417848  # 0x80010108
RPC_S_SERVER_UNAVAILABLE = -2147023174  # 0x800706BA
RPC_S_CALL_FAILED = -2147023170  # 0x800706BE
DISP_E_MEMBERNOTFOUND = -2147352573  # 0x80020003
DISP_E_TYPEMISMATCH = -2147352571  # 0x80020005

_HRESULT_IN_TEXT = re.compile(r"\((-\d{9,10}),")

OPERATION_FAILED = "operation_failed"
INTERNAL = "internal"
INVALID_INPUT = "invalid_input"
NOT_SUPPORTED = "not_supported"
NOT_SUPPORTED_HINT = (
    "The active adapter cannot perform this operation. Use the real SolidWorks "
    "adapter, another tool, or do this step in SolidWorks directly."
)


@dataclass(frozen=True)
class Classification:
    """The category of a failure and the next step to suggest."""

    error_type: str
    hint: str


@dataclass(frozen=True)
class ErrorRule:
    """Matches a failure by HRESULT and/or a case-insensitive message pattern."""

    error_type: str
    hint: str
    hresults: frozenset[int] = field(default_factory=frozenset)
    patterns: tuple[str, ...] = ()

    def matches(self, message: str, hresult: int | None) -> bool:
        """Return True when the HRESULT or any pattern matches."""
        if hresult is not None and hresult in self.hresults:
            return True
        return any(re.search(p, message, re.IGNORECASE) for p in self.patterns)


DEFAULT_RULES: tuple[ErrorRule, ...] = (
    ErrorRule(
        error_type="solidworks_unavailable",
        hint=(
            "SolidWorks is not reachable - it was closed or crashed. Restart "
            "SolidWorks (and the MCP server if it still fails), then retry."
        ),
        hresults=frozenset(
            {RPC_E_DISCONNECTED, RPC_S_SERVER_UNAVAILABLE, RPC_S_CALL_FAILED}
        ),
        patterns=(
            r"rpc server is unavailable",
            r"object invoked has disconnected",
            r"not connected to solidworks",
            r"solidworks (application )?(is )?not connected",
        ),
    ),
    ErrorRule(
        error_type="com_wrong_thread",
        hint=(
            "A SolidWorks call ran off the thread that connected - a server "
            "bug. Report the tool name; restart the MCP server to recover."
        ),
        patterns=(r"belong to the thread that called connect",),
    ),
    ErrorRule(
        error_type="circuit_open",
        hint=(
            "Calls to this operation are paused after repeated failures. Fix "
            "the underlying error, then retry after the breaker timeout."
        ),
        patterns=(r"circuit breaker is (open|half[_-]open)",),
    ),
    ErrorRule(
        error_type="com_member_not_found",
        hint=(
            "SolidWorks could not resolve this API member - usually a stale "
            "type cache. Delete %TEMP%\\gen_py and restart the MCP server."
        ),
        hresults=frozenset({DISP_E_MEMBERNOTFOUND}),
        patterns=(r"member not found",),
    ),
    ErrorRule(
        error_type="com_type_mismatch",
        hint=(
            "SolidWorks rejected an argument's COM type. This is a server bug; "
            "report the tool name and arguments."
        ),
        hresults=frozenset({DISP_E_TYPEMISMATCH}),
        patterns=(r"type mismatch",),
    ),
    ErrorRule(
        error_type=NOT_SUPPORTED,
        hint=NOT_SUPPORTED_HINT,
        patterns=(
            r"does not support",
            r"no adapter capability",
            r"only available on windows",
            r"not available",
        ),
    ),
    ErrorRule(
        error_type="wrong_document_type",
        hint=(
            "The active document is the wrong kind for this tool. Create or "
            "activate the right one (create_part, create_assembly, "
            "create_drawing or activate_document), then retry."
        ),
        patterns=(
            r"(requires|needs) an? (active )?(part|assembly|drawing)"
            r"( or (part|assembly|drawing))? document",
        ),
    ),
    ErrorRule(
        error_type="no_active_sketch",
        hint="Create or open a sketch first (create_sketch), then retry.",
        patterns=(r"no active sketch",),
    ),
    ErrorRule(
        error_type="no_active_document",
        hint=(
            "Open or create a document first (open_model / create_part), or "
            "activate one with activate_document, then retry."
        ),
        patterns=(r"no active (model|document)",),
    ),
    ErrorRule(
        error_type="not_found",
        hint=(
            "Check the name or path - list what exists first (list_features, "
            "list_open_documents, list_drawing_views) and use an exact name."
        ),
        patterns=(
            r"\bnot found\b",
            r"does not exist",
            r"\bno such\b",
            r"\bno [\w.-]+( \w+)? found\b",
            r"\bhas no (\w+ )?(edges|faces)\b",
            r"\bhas no [\w-]+ body\b",
            r"\bno view named\b",
        ),
    ),
)

_FALLBACK_HINTS = {
    OPERATION_FAILED: (
        "The SolidWorks operation failed. Read the message for the cause, "
        "adjust the inputs, and retry."
    ),
    INTERNAL: (
        "Unexpected server error - this is a bug, not a modelling problem. "
        "Report the tool name, arguments and this message."
    ),
}


def extract_hresult(message: str, exc: BaseException | None = None) -> int | None:
    """Return the COM HRESULT from a ``com_error`` or from flattened text."""
    if exc is not None:
        args = getattr(exc, "args", ())
        if args and isinstance(args[0], int):
            return args[0]
    match = _HRESULT_IN_TEXT.search(message)
    return int(match.group(1)) if match else None


class ErrorClassifier:
    """Map a failure to a :class:`Classification` using ordered rules."""

    def __init__(self, rules: tuple[ErrorRule, ...] = DEFAULT_RULES) -> None:
        self._rules = rules

    def classify(
        self,
        message: str,
        exc: BaseException | None = None,
        *,
        fallback: str = OPERATION_FAILED,
    ) -> Classification:
        """Classify ``message`` (and ``exc`` when there is one).

        Args:
            message: The error text the caller will see.
            exc: The exception, when the failure was raised rather than returned.
            fallback: Category for an unrecognised failure: ``operation_failed``
                for adapter errors, ``internal`` for unexpected exceptions.

        Returns:
            Classification: The first matching rule, else the fallback.
        """
        hresult = extract_hresult(message, exc)
        for rule in self._rules:
            if rule.matches(message, hresult):
                return Classification(rule.error_type, rule.hint)
        return Classification(fallback, _FALLBACK_HINTS[fallback])
