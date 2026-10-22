"""Tests for the package."""

from __future__ import annotations

import pytest


class TestInitCoverage:
    """Test init coverage."""

    def test_lazy_load_create_server(self):
        """Lines 40-46 — __getattr__ loads create_server on demand."""
        import solidworks_mcp as sw

        fn = sw.create_server
        assert callable(fn)

    def test_lazy_load_main(self):
        """Lines 40-46 — __getattr__ loads main on demand."""
        import solidworks_mcp as sw

        fn = sw.main
        assert callable(fn)

    def test_getattr_invalid_raises_attribute_error(self):
        """Line 48 — unknown attribute raises AttributeError."""
        import solidworks_mcp as sw

        with pytest.raises(AttributeError):
            _ = sw.totally_nonexistent_symbol_xyz

    def test_dir_includes_public_api(self):
        """Line 58 — __dir__ returns sorted public names."""
        import solidworks_mcp as sw

        d = dir(sw)
        assert "create_server" in d
        assert "main" in d
        assert "SolidWorksMCPConfig" in d
        assert "__version__" in d
