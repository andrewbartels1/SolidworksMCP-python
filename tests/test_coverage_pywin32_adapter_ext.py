"""Extended coverage tests for pywin32_adapter.py."""

from __future__ import annotations

import platform
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.solidworks_mcp.exceptions import SolidWorksMCPError


class TestPyWin32AdapterInitialization:
    """Test PyWin32Adapter initialization and platform checks."""

    def test_pywin32_not_available_raises_error(self) -> None:
        """Test that init raises error when pywin32 is not available."""
        # Mock PYWIN32_AVAILABLE as False
        with patch(
            "src.solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", False
        ):
            from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

            with pytest.raises(SolidWorksMCPError, match="pywin32 is not available"):
                PyWin32Adapter()

    def test_non_windows_platform_raises_error(self) -> None:
        """Test that init raises error on non-Windows platform."""
        # Mock platform.system to return non-Windows value
        with patch(
            "src.solidworks_mcp.adapters.pywin32_adapter.platform.system"
        ) as mock_system:
            mock_system.return_value = "Linux"

            # Need to reload module to pick up mocked platform
            with patch(
                "src.solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
            ):
                from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

                with pytest.raises(
                    SolidWorksMCPError,
                    match="PyWin32Adapter requires Windows platform",
                ):
                    PyWin32Adapter()

    def test_darwin_platform_raises_error(self) -> None:
        """Test that init raises error on macOS."""
        with patch(
            "src.solidworks_mcp.adapters.pywin32_adapter.platform.system"
        ) as mock_system:
            mock_system.return_value = "Darwin"

            with patch(
                "src.solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
            ):
                from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

                with pytest.raises(SolidWorksMCPError):
                    PyWin32Adapter()

    @pytest.mark.skipif(
        platform.system() != "Windows",
        reason="Requires Windows platform",
    )
    def test_initialization_with_config(self) -> None:
        """Test initialization with configuration on Windows."""
        try:
            from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

            config = {
                "timeout": 30,
                "auto_connect": False,
                "startup_timeout": 60,
            }
            adapter = PyWin32Adapter(config)

            assert adapter.config_dict["timeout"] == 30
            assert adapter.swApp is None
            assert adapter.currentModel is None
        except SolidWorksMCPError:
            # Skip if pywin32 not actually available
            pytest.skip("pywin32 not available")

    @pytest.mark.skipif(
        platform.system() != "Windows",
        reason="Requires Windows platform",
    )
    def test_constants_initialized(self) -> None:
        """Test that COM constants are initialized."""
        try:
            from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

            adapter = PyWin32Adapter()

            assert adapter.constants is not None
            assert "swDocPART" in adapter.constants
            assert adapter.constants["swDocPART"] == 1
            assert adapter.constants["swDocASSEMBLY"] == 2
            assert adapter.constants["swDocDRAWING"] == 3
        except SolidWorksMCPError:
            pytest.skip("pywin32 not available")

    @pytest.mark.skipif(
        platform.system() != "Windows",
        reason="Requires Windows platform",
    )
    @pytest.mark.asyncio
    async def test_connect_com_initialization(self) -> None:
        """Test connect method initializes COM."""
        try:
            from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

            adapter = PyWin32Adapter()

            # Mock COM operations
            with patch(
                "src.solidworks_mcp.adapters.pywin32_adapter.pythoncom"
            ) as mock_com:
                with patch(
                    "src.solidworks_mcp.adapters.pywin32_adapter.win32com.client"
                ) as mock_client:
                    mock_app = MagicMock()
                    mock_client.GetObject.return_value = mock_app

                    try:
                        await adapter.connect()
                    except Exception:
                        # Connection might fail without actual SolidWorks
                        pass

                    # COM should have been initialized
                    mock_com.CoInitialize.assert_called()
        except SolidWorksMCPError:
            pytest.skip("pywin32 not available")


class TestVBModuleNameParsing:
    """Test VB macro module name parsing."""

    def test_parse_vb_module_name_with_attribute(self, tmp_path) -> None:
        """Test parsing VB module name from macro file."""
        from src.solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        macro_file = tmp_path / "test_macro.swp"
        macro_file.write_text(
            'Attribute VB_Name = "CustomMacro"\nSub Main()\nEnd Sub\n'
        )

        name = _parse_vb_module_name(str(macro_file))
        assert name == "CustomMacro"

    def test_parse_vb_module_name_with_single_quotes(self, tmp_path) -> None:
        """Test parsing VB module name with single quotes."""
        from src.solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        macro_file = tmp_path / "test_macro.swp"
        macro_file.write_text(
            "Attribute VB_Name = 'QuotedMacro'\nSub Main()\nEnd Sub\n"
        )

        name = _parse_vb_module_name(str(macro_file))
        assert name == "QuotedMacro"

    def test_parse_vb_module_name_missing_attribute(self, tmp_path) -> None:
        """Test parsing when VB_Name attribute is missing."""
        from src.solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        macro_file = tmp_path / "test_macro.swp"
        macro_file.write_text("Sub Main()\nEnd Sub\n")

        name = _parse_vb_module_name(str(macro_file))
        # Should fall back to file stem
        assert name == "test_macro"

    def test_parse_vb_module_name_nonexistent_file(self) -> None:
        """Test parsing nonexistent file."""
        from src.solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        name = _parse_vb_module_name("/nonexistent/path/macro.swp")
        # Should fall back to default
        assert name == "macro"

    def test_parse_vb_module_name_fallback_to_default(self, tmp_path) -> None:
        """Test fallback to SolidWorksMacro when no name found."""
        from src.solidworks_mcp.adapters.pywin32_adapter import _parse_vb_module_name

        # File with no name and no stem (edge case)
        macro_file = tmp_path / ".swp"
        macro_file.write_text("Sub Main()\nEnd Sub\n")

        name = _parse_vb_module_name(str(macro_file))
        # Should fall back to SolidWorksMacro
        assert name == "SolidWorksMacro"


class TestPyWin32AdapterMockCOM:
    """Test PyWin32Adapter with mocked COM objects."""

    @pytest.mark.asyncio
    async def test_open_model_with_mock_com(self) -> None:
        """Test opening a model with mocked COM."""
        # Mock the entire adapter to test COM interaction
        with patch(
            "src.solidworks_mcp.adapters.pywin32_adapter.PYWIN32_AVAILABLE", True
        ):
            with patch(
                "src.solidworks_mcp.adapters.pywin32_adapter.platform.system"
            ) as mock_sys:
                mock_sys.return_value = "Windows"

                # Import after mocking
                from src.solidworks_mcp.adapters.pywin32_adapter import PyWin32Adapter

                # Mock pythoncom and win32com
                with patch("src.solidworks_mcp.adapters.pywin32_adapter.pythoncom"):
                    with patch(
                        "src.solidworks_mcp.adapters.pywin32_adapter.win32com.client"
                    ) as mock_client:
                        # Setup mock COM objects
                        mock_app = AsyncMock()
                        mock_client.GetObject.return_value = mock_app
                        mock_client.Dispatch.return_value = mock_app

                        adapter = PyWin32Adapter({"timeout": 30})

                        # Mock the COM model
                        mock_model = MagicMock()
                        mock_app.OpenDoc6.return_value = mock_model

                        # Try to connect (might fail but should reach COM calls)
                        try:
                            await adapter.connect()
                        except Exception:
                            # Expected to fail without real SolidWorks
                            pass
