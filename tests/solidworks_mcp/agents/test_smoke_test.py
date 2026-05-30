"""Direct branch tests for solidworks_mcp.agents.smoke_test."""

from __future__ import annotations

import asyncio
import runpy
import sys
import warnings


def test_run_selects_reconstruction_schema(monkeypatch) -> None:
    import solidworks_mcp.agents.smoke_test as smoke

    captured: dict[str, object] = {}

    async def _fake_run_validated_prompt(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(smoke, "run_validated_prompt", _fake_run_validated_prompt)
    monkeypatch.setattr(smoke, "pretty_json", lambda result: str(result))
    monkeypatch.setattr(smoke.typer, "echo", lambda *_args, **_kwargs: None)

    code = asyncio.run(
        smoke._run(
            agent_file="a.agent.md",
            model_name="github:openai/gpt-4.1",
            prompt="reconstruct",
            schema=smoke.SchemaChoice.reconstruction,
            max_retries_on_recoverable=1,
        )
    )

    assert code == 0
    assert captured["result_type"] is smoke.ReconstructionPlan


def test_main_module_calls_app(monkeypatch) -> None:
    calls = {"app": 0}

    class _DummyTyper:
        def __init__(self, *args, **kwargs):
            pass

        def command(self, *args, **kwargs):
            return lambda fn: fn

        def __call__(self, *args, **kwargs):
            calls["app"] += 1

    monkeypatch.setattr("typer.Typer", _DummyTyper)
    sys.modules.pop("solidworks_mcp.agents.smoke_test", None)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=RuntimeWarning,
            message=".*found in sys.modules.*",
        )
        runpy.run_module("solidworks_mcp.agents.smoke_test", run_name="__main__")
    assert calls["app"] == 1
