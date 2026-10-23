"""Tests for the tool error classifier (spec: tools/error-boundary)."""

from __future__ import annotations

import pytest

from solidworks_mcp.tools.error_classifier import (
    DISP_E_MEMBERNOTFOUND,
    DISP_E_TYPEMISMATCH,
    INTERNAL,
    OPERATION_FAILED,
    RPC_E_DISCONNECTED,
    RPC_S_CALL_FAILED,
    RPC_S_SERVER_UNAVAILABLE,
    ErrorClassifier,
    ErrorRule,
    extract_hresult,
)


class _ComError(Exception):
    """Stand-in for ``pywintypes.com_error`` (args[0] is the HRESULT)."""


@pytest.fixture
def classifier() -> ErrorClassifier:
    return ErrorClassifier()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "COM error in add_line: (-2147023174, 'The RPC server is unavailable.', None, None)",
            "solidworks_unavailable",
        ),
        (
            f"COM error in close_model: ({RPC_E_DISCONNECTED}, 'disconnected', None, None)",
            "solidworks_unavailable",
        ),
        (
            f"COM error in create_part: ({RPC_S_CALL_FAILED}, 'call failed', None, None)",
            "solidworks_unavailable",
        ),
        ("Not connected to SolidWorks", "solidworks_unavailable"),
        ("SolidWorks application is not connected", "solidworks_unavailable"),
        ("Circuit breaker is open for select_feature", "circuit_open"),
        ("Circuit breaker is half_open for add_line", "circuit_open"),
        (
            f"COM error in x: ({DISP_E_MEMBERNOTFOUND}, 'Member not found.', None, None)",
            "com_member_not_found",
        ),
        ("Error in get_model_info: Member not found", "com_member_not_found"),
        (
            f"COM error in x: ({DISP_E_TYPEMISMATCH}, 'Type mismatch.', None, None)",
            "com_type_mismatch",
        ),
        ("No active sketch", "no_active_sketch"),
        ("No active sketch to exit", "no_active_sketch"),
        ("No active model", "no_active_document"),
        ("No active document", "no_active_document"),
        ("Feature not found: Boss-Extrude9", "not_found"),
        ("Model file not found: C:/x.sldprt", "not_found"),
        ("Configuration 'X' does not exist", "not_found"),
        (
            "The selected face has no circular edges (face centre [30, 10, 20] mm).",
            "not_found",
        ),
        ("The selected face has no edges", "not_found"),
        ("No face found at point [1000, 1000, 1000] mm.", "not_found"),
        ("The active part has no solid body faces.", "not_found"),
        ("No view named 'Side'. Views: Front, Top", "not_found"),
        ("No drawing views found to dimension (pictorial ...)", "not_found"),
        (
            "This operation requires a drawing document (active document type is 1).",
            "wrong_document_type",
        ),
        ("select_face_edges requires an active part document", "wrong_document_type"),
        ("save_body_as_part requires an active part document", "wrong_document_type"),
        (
            "get_material needs an active part document (active document is drawing).",
            "wrong_document_type",
        ),
        (
            "list_model_dimensions needs an active part or assembly document",
            "wrong_document_type",
        ),
        ("No dimensions found on feature 'Fillet9'", "not_found"),
        ("No entity found for 'Edge<9>'; check the name", "not_found"),
        ("No .sldmat libraries found in: C:/x", "not_found"),
        ("The active part has no sheet-metal body", "not_found"),
    ],
)
def test_known_messages_are_categorised(
    classifier: ErrorClassifier, message: str, expected: str
) -> None:
    result = classifier.classify(message)

    assert result.error_type == expected
    assert result.hint


def test_hresult_from_exception_wins_over_unrelated_text(
    classifier: ErrorClassifier,
) -> None:
    exc = _ComError(RPC_S_SERVER_UNAVAILABLE, "text", None, None)

    result = classifier.classify("something odd", exc)

    assert result.error_type == "solidworks_unavailable"


def test_unrecognised_adapter_error_falls_back_to_operation_failed(
    classifier: ErrorClassifier,
) -> None:
    result = classifier.classify("Failed to create extrusion")

    assert result.error_type == OPERATION_FAILED
    assert "retry" in result.hint


def test_unrecognised_exception_uses_the_internal_fallback(
    classifier: ErrorClassifier,
) -> None:
    result = classifier.classify(
        "division by zero", ZeroDivisionError(), fallback=INTERNAL
    )

    assert result.error_type == INTERNAL
    assert "bug" in result.hint


def test_first_matching_rule_wins() -> None:
    rules = (
        ErrorRule("first", "h1", patterns=(r"boom",)),
        ErrorRule("second", "h2", patterns=(r"boom",)),
    )

    assert ErrorClassifier(rules).classify("boom").error_type == "first"


@pytest.mark.parametrize(
    ("message", "exc", "expected"),
    [
        ("COM error in a: (-2147352573, 'x', None, None)", None, DISP_E_MEMBERNOTFOUND),
        ("no code here", None, None),
        ("ignored", _ComError(-5, "x"), -5),
        (
            "COM error in a: (-2147352571, 'x')",
            _ComError("not-an-int"),
            DISP_E_TYPEMISMATCH,
        ),
    ],
)
def test_extract_hresult(
    message: str, exc: BaseException | None, expected: int | None
) -> None:
    assert extract_hresult(message, exc) == expected


def test_wrong_thread_is_its_own_category() -> None:
    from solidworks_mcp.tools.error_classifier import ErrorClassifier

    found = ErrorClassifier().classify(
        "get_model_info was called from thread 'w', but SolidWorks COM objects "
        "belong to the thread that called connect()."
    )

    assert found.error_type == "com_wrong_thread"
    assert "restart the MCP server" in found.hint
