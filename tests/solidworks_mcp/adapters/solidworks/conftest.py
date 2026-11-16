"""Fixtures for the real adapter's unit tests."""

from __future__ import annotations

import pytest

from solidworks_mcp.adapters.solidworks import hole_library, part_features


@pytest.fixture(autouse=True)
def sample_hole_library(monkeypatch: pytest.MonkeyPatch) -> hole_library.HoleLibrary:
    """Size holes from the built-in sample, never the machine's Toolbox file.

    ``test_hole_library.py`` tests the real lookup through the module itself.
    """
    library = hole_library.sample_library()
    monkeypatch.setattr(part_features, "find_library", lambda: library)
    return library
