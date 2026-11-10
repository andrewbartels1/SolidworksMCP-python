"""Tests for the shared input base and the removed-inputs table."""

from __future__ import annotations

from solidworks_mcp.tools.input_compat import (
    REMOVED_INPUTS,
    CompatInput,
    removed_inputs,
)


class _Thing(CompatInput):
    name: str


def test_removed_inputs_name_each_field_sent_with_its_pointer(monkeypatch) -> None:
    monkeypatch.setitem(REMOVED_INPUTS, "_Thing", {"old": "use `new`", "gone": "x"})

    sent = _Thing(name="a", old=1, other=2)

    assert removed_inputs(sent) == ["`old` is no longer an input: use `new`"]
    assert removed_inputs(_Thing(name="a")) == []


def test_a_model_without_removed_inputs_is_never_refused() -> None:
    class _Free(CompatInput):
        pass

    assert removed_inputs(_Free(anything=1)) == []


def test_every_removed_field_is_really_gone_from_its_model() -> None:
    """A field still declared would never reach model_extra, so never be refused."""
    from importlib import import_module
    from pkgutil import iter_modules

    import solidworks_mcp.tools as tools_pkg

    models: dict[str, type] = {}
    for info in iter_modules(tools_pkg.__path__):
        module = import_module(f"solidworks_mcp.tools.{info.name}")
        for value in vars(module).values():
            if isinstance(value, type) and issubclass(value, CompatInput):
                models[value.__name__] = value
    for model_name, fields in REMOVED_INPUTS.items():
        assert model_name in models, model_name
        assert not set(fields) & set(models[model_name].model_fields), model_name
