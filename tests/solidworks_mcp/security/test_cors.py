"""Branch coverage tests for src.solidworks_mcp.security.cors."""

from __future__ import annotations

from types import SimpleNamespace

from src.solidworks_mcp.security.cors import setup_cors


def test_setup_cors_prefers_cors_origins() -> None:
    mcp = SimpleNamespace()
    cfg = SimpleNamespace(
        enable_cors=True,
        cors_origins=["https://a.example"],
        allowed_origins=["https://b.example"],
    )

    setup_cors(mcp, cfg)

    assert mcp._security_cors_enabled is True
    assert mcp._security_cors_origins == ["https://a.example"]


def test_setup_cors_falls_back_to_allowed_origins() -> None:
    mcp = SimpleNamespace()
    cfg = SimpleNamespace(
        enable_cors=False, cors_origins=[], allowed_origins=["https://b.example"]
    )

    setup_cors(mcp, cfg)

    assert mcp._security_cors_enabled is False
    assert mcp._security_cors_origins == ["https://b.example"]


def test_setup_cors_handles_plain_object_without_attributes() -> None:
    cfg = SimpleNamespace(
        enable_cors=True, cors_origins=["https://a.example"], allowed_origins=[]
    )
    # object() has no writable __dict__, so assignment inside setup_cors hits AttributeError branch.
    setup_cors(object(), cfg)
