"""Tests for test adapters factory coverage."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.solidworks_mcp.adapters.factory import (
    AdapterFactory,
    _register_default_adapters,
)
from src.solidworks_mcp.adapters.vba_adapter import VbaGeneratorAdapter
from src.solidworks_mcp.config import AdapterType


class _DummyAdapter:
    """Test dummy adapter."""

    def __init__(self, config):
        """Test init."""

        self.config = config


def _base_config(**overrides):
    """Test base config."""

    base = {
        "testing": False,
        "mock_solidworks": False,
        "adapter_type": AdapterType.PYWIN32,
        "enable_circuit_breaker": False,
        "enable_connection_pooling": False,
        "solidworks_path": "mock://solidworks",
        "enable_windows_validation": False,
        "debug": False,
        "circuit_breaker_threshold": 2,
        "circuit_breaker_timeout": 5,
        "connection_pool_size": 2,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_create_adapter_raises_for_unregistered_adapter_type(monkeypatch) -> None:
    """Test create adapter raises for unregistered adapter type."""

    factory = AdapterFactory()
    monkeypatch.setattr(factory, "_adapter_registry", {AdapterType.MOCK: _DummyAdapter})
    monkeypatch.setattr(
        "src.solidworks_mcp.adapters.factory.platform.system", lambda: "Windows"
    )

    with pytest.raises(ValueError, match="Adaptertype"):
        factory._create_adapter_impl(_base_config(adapter_type=AdapterType.PYWIN32))


def test_create_adapter_vba_uses_backing_adapter_with_built_config(monkeypatch) -> None:
    """Test create adapter vba uses backing adapter with built config."""

    factory = AdapterFactory()
    monkeypatch.setattr(
        factory,
        "_adapter_registry",
        {
            AdapterType.VBA: VbaGeneratorAdapter,
            AdapterType.PYWIN32: _DummyAdapter,
            AdapterType.MOCK: _DummyAdapter,
        },
    )
    monkeypatch.setattr(
        "src.solidworks_mcp.adapters.factory.platform.system", lambda: "Windows"
    )

    adapter = factory._create_adapter_impl(_base_config(adapter_type=AdapterType.VBA))

    assert isinstance(adapter, VbaGeneratorAdapter)
    assert isinstance(adapter._backing_adapter, _DummyAdapter)
    assert adapter._backing_adapter.config["solidworks_path"] == "mock://solidworks"


def test_create_adapter_vba_raises_when_backing_type_unregistered(monkeypatch) -> None:
    """Test create adapter vba raises when backing type unregistered."""

    factory = AdapterFactory()
    monkeypatch.setattr(
        factory,
        "_adapter_registry",
        {
            AdapterType.VBA: VbaGeneratorAdapter,
            AdapterType.MOCK: _DummyAdapter,
        },
    )
    monkeypatch.setattr(
        "src.solidworks_mcp.adapters.factory.platform.system", lambda: "Windows"
    )

    with pytest.raises(ValueError, match="Backing adapter type"):
        factory._create_adapter_impl(_base_config(adapter_type=AdapterType.VBA))


def test_determine_vba_backing_type_paths(monkeypatch) -> None:
    """Test determine vba backing type paths."""

    factory = AdapterFactory()

    assert (
        factory._determine_vba_backing_type(_base_config(testing=True))
        == AdapterType.MOCK
    )
    assert (
        factory._determine_vba_backing_type(_base_config(mock_solidworks=True))
        == AdapterType.MOCK
    )

    monkeypatch.setattr(
        "src.solidworks_mcp.adapters.factory.platform.system", lambda: "Linux"
    )
    assert factory._determine_vba_backing_type(_base_config()) == AdapterType.MOCK

    monkeypatch.setattr(
        "src.solidworks_mcp.adapters.factory.platform.system", lambda: "Windows"
    )
    assert factory._determine_vba_backing_type(_base_config()) == AdapterType.PYWIN32


def test_build_adapter_config_values() -> None:
    """Test build adapter config values."""

    factory = AdapterFactory()
    cfg = _base_config(
        solidworks_path="C:/SW/SLDWORKS.exe",
        enable_windows_validation=True,
        debug=True,
    )

    adapter_cfg = factory._build_adapter_config(cfg)
    assert adapter_cfg["solidworks_path"] == "C:/SW/SLDWORKS.exe"
    assert adapter_cfg["enable_windows_validation"] is True
    assert adapter_cfg["debug"] is True
    assert adapter_cfg["timeout"] == 30
    assert adapter_cfg["retry_attempts"] == 3


def test_register_default_adapters_handles_pywin32_importerror(monkeypatch) -> None:
    """Test register default adapters handles pywin32 importerror."""

    AdapterFactory._adapter_registry.clear()
    monkeypatch.setattr(
        "src.solidworks_mcp.adapters.factory.platform.system", lambda: "Windows"
    )

    import builtins

    original_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        """Test fake import."""

        if name.endswith("pywin32_adapter"):
            raise ImportError("pywin32 not available")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    _register_default_adapters()

    assert AdapterType.MOCK in AdapterFactory._adapter_registry
    assert AdapterType.VBA in AdapterFactory._adapter_registry
