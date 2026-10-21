"""Tests for solidworks_mcp.ui.services.docs_service."""

from __future__ import annotations

from pathlib import Path

import pytest

from solidworks_mcp.ui.services.docs_service import fetch_docs_context


def test_fetch_docs_context_rejects_non_http_origins(tmp_path: Path) -> None:
    """Only http(s) docs endpoints are fetched (no file:// or ftp:// reads)."""
    with pytest.raises(ValueError, match="Disallowed URL scheme in docs endpoint"):
        fetch_docs_context(
            "s1", db_path=tmp_path / "db.sqlite3", api_origin="file:///etc"
        )
