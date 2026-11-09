"""The selftest command: precheck, exit codes, and the run against a server."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastmcp import FastMCP
from typer.testing import CliRunner

from solidworks_mcp.adapters.mock_adapter import MockSolidWorksAdapter
from solidworks_mcp.config import SolidWorksMCPConfig
from solidworks_mcp.selftest import cli
from solidworks_mcp.selftest.results import AreaResult, Outcome
from solidworks_mcp.tools import register_tools


@pytest.mark.parametrize(
    ("system", "versions", "running", "message"),
    [
        ("Linux", [2026], True, "needs Windows"),
        ("Windows", [], True, "No SolidWorks install"),
        ("Windows", [2026], False, "SolidWorks isn't running"),
        ("Windows", [2026], True, None),
    ],
)
def test_precheck(system, versions, running, message) -> None:
    problem = cli.precheck(lambda: system, lambda: versions, lambda: running)
    if message is None:
        assert problem is None
    else:
        assert message in problem


@pytest.mark.parametrize(
    ("stdout", "running"),
    [("SLDWORKS.exe  1234 Console", True), ("INFO: No tasks", False)],
)
def test_solidworks_running_reads_tasklist(monkeypatch, stdout, running) -> None:
    seen = {}

    def _run(args, **kwargs):
        seen["args"] = args
        return SimpleNamespace(stdout=stdout)

    monkeypatch.setattr(cli.subprocess, "run", _run)

    assert cli.solidworks_running() is running
    assert seen["args"][:2] == ["tasklist", "/FI"]


async def _mock_server(config: SolidWorksMCPConfig) -> SimpleNamespace:
    adapter = MockSolidWorksAdapter({})
    await adapter.connect()
    mcp = FastMCP("selftest-test")
    await register_tools(mcp, adapter, config)
    return SimpleNamespace(mcp=mcp, adapter=adapter)


@pytest.mark.asyncio
async def test_a_run_against_the_mock_fails_and_writes_the_report(
    tmp_path: Path, capsys
) -> None:
    config = SolidWorksMCPConfig()
    config.solidworks_year = 2026
    report = tmp_path / "selftest.md"

    code = await cli.run_selftest(config, report, _mock_server)

    out = capsys.readouterr().out
    assert code == cli.EXIT_FAIL
    assert "FAIL  part" in out
    assert "SKIP  assembly" in out
    assert report.read_text(encoding="utf-8").startswith("### Selftest: 0 of 4")
    assert f"Summary written to {report}" in out


@pytest.mark.asyncio
async def test_every_area_passing_exits_zero(monkeypatch) -> None:
    async def _all_pass(areas, ctx):
        return [AreaResult(a.name, Outcome.PASS) for a in areas]

    monkeypatch.setattr(cli, "run_areas", _all_pass)

    code = await cli.run_selftest(SolidWorksMCPConfig(), None, _mock_server)

    assert code == cli.EXIT_PASS


@pytest.mark.asyncio
async def test_a_connect_failure_cannot_run(capsys) -> None:
    async def _refuse(_config):
        raise RuntimeError("SldWorks.Application not found")

    code = await cli.run_selftest(SolidWorksMCPConfig(), None, _refuse)

    assert code == cli.EXIT_CANNOT_RUN
    assert (
        "Could not connect to SolidWorks: SldWorks.Application not found"
        in capsys.readouterr().out
    )


@pytest.mark.asyncio
async def test_start_server_builds_and_connects_the_real_server() -> None:
    config = SolidWorksMCPConfig(mock_solidworks=True)

    server = await cli._start_server(config)
    try:
        assert server.adapter.is_connected()
        assert "verify_model" in {t.name for t in await server.mcp.list_tools()}
    finally:
        await server.adapter.disconnect()


def test_command_exits_two_when_precheck_fails(monkeypatch) -> None:
    monkeypatch.setattr(cli, "precheck", lambda: cli.NOT_RUNNING)

    result = CliRunner().invoke(cli.app, [])

    assert result.exit_code == cli.EXIT_CANNOT_RUN
    assert cli.NOT_RUNNING in result.output


def test_command_refuses_a_mock_only_setup(monkeypatch) -> None:
    monkeypatch.setattr(cli, "precheck", lambda: None)
    monkeypatch.setattr(cli, "installed_versions", lambda: [2026])
    monkeypatch.setattr(
        SolidWorksMCPConfig, "can_use_solidworks", property(lambda self: False)
    )

    result = CliRunner().invoke(cli.app, [])

    assert result.exit_code == cli.EXIT_CANNOT_RUN
    assert "the selftest needs SolidWorks" in result.output


def test_command_runs_with_the_newest_year_by_default(monkeypatch) -> None:
    seen = {}

    async def _run(config, report_path):
        seen["year"], seen["report"] = config.solidworks_year, report_path
        return cli.EXIT_PASS

    monkeypatch.setattr(cli, "precheck", lambda: None)
    monkeypatch.setattr(cli, "installed_versions", lambda: [2026, 2024])
    monkeypatch.setattr(
        SolidWorksMCPConfig, "can_use_solidworks", property(lambda self: True)
    )
    monkeypatch.setattr(cli, "run_selftest", _run)
    monkeypatch.setattr("solidworks_mcp.utils.setup_logging", lambda config: None)

    result = CliRunner().invoke(cli.app, ["--report", "out.md"])

    assert result.exit_code == cli.EXIT_PASS, result.output
    assert seen == {"year": 2026, "report": Path("out.md")}
    assert "Testing SolidWorks 2026" in result.output
