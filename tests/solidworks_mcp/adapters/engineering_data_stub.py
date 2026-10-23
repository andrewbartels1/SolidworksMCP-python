"""A recording stub for the engineering-data adapter methods, shared by the
wrapper-adapter tests (circuit breaker and connection pool)."""

from __future__ import annotations

from typing import Any

from solidworks_mcp.adapters.base import AdapterResult, AdapterResultStatus


class EngineeringDataStub:
    """Records every engineering-data call and answers SUCCESS."""

    EXPECTED_CALLS = [
        ("list_model_dimensions", ("Sketch1",)),
        ("measure_entities", (["Edge<1>"],)),
        ("get_material", ("Default",)),
        ("set_material", ("AISI 1020", "SOLIDWORKS Materials", "Default")),
        ("list_available_materials", ("steel",)),
        ("get_custom_properties", ("Default",)),
        ("set_custom_property", ("PartNo", "P-1", "Default")),
        ("export_flat_pattern", ("flat.dxf",)),
    ]

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _record(self, name: str, *args: Any) -> AdapterResult[Any]:
        self.calls.append((name, args))
        return AdapterResult(status=AdapterResultStatus.SUCCESS, data=name)

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    def is_connected(self) -> bool:
        return True

    async def list_model_dimensions(self, feature_name=None):
        return self._record("list_model_dimensions", feature_name)

    async def measure_entities(self, entities):
        return self._record("measure_entities", entities)

    async def get_material(self, configuration=None):
        return self._record("get_material", configuration)

    async def set_material(self, material_name, database=None, configuration=None):
        return self._record("set_material", material_name, database, configuration)

    async def list_available_materials(self, search=None):
        return self._record("list_available_materials", search)

    async def get_custom_properties(self, configuration=None):
        return self._record("get_custom_properties", configuration)

    async def set_custom_property(self, name, value, configuration=None):
        return self._record("set_custom_property", name, value, configuration)

    async def export_flat_pattern(self, file_path):
        return self._record("export_flat_pattern", file_path)


async def exercise_engineering_data(wrapped: Any) -> None:
    """Call every engineering-data method once through ``wrapped``."""
    results = [
        await wrapped.list_model_dimensions("Sketch1"),
        await wrapped.measure_entities(["Edge<1>"]),
        await wrapped.get_material("Default"),
        await wrapped.set_material("AISI 1020", "SOLIDWORKS Materials", "Default"),
        await wrapped.list_available_materials("steel"),
        await wrapped.get_custom_properties("Default"),
        await wrapped.set_custom_property("PartNo", "P-1", "Default"),
        await wrapped.export_flat_pattern("flat.dxf"),
    ]
    assert all(r.is_success for r in results), [r.error for r in results]
