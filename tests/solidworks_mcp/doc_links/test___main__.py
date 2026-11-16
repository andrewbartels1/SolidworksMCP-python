"""``python -m solidworks_mcp.doc_links`` (spec: docs/llms-txt, docs/link-check)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import httpx
import pytest

from solidworks_mcp.doc_links import __main__ as cli
from solidworks_mcp.doc_links.llms_txt import LLMS_TXT


def test_build_then_check_pass(site_root: Path) -> None:
    assert cli.main(["build", "--root", str(site_root)]) == 0
    assert (site_root / LLMS_TXT).read_text(encoding="utf-8").startswith("# Proj\n")
    assert cli.main(["check", "--root", str(site_root)]) == 0


def test_build_fails_on_a_bad_page(site_root: Path) -> None:
    (site_root / "docs/index.md").write_text("no heading\n", encoding="utf-8")

    assert cli.main(["build", "--root", str(site_root)]) == 1
    assert not (site_root / LLMS_TXT).exists()


def test_check_fails_on_a_broken_link(site_root: Path) -> None:
    cli.main(["build", "--root", str(site_root)])
    page = site_root / "docs/guide/more.md"
    page.write_text(
        page.read_text(encoding="utf-8") + "\n[x](gone.md)\n", encoding="utf-8"
    )

    assert cli.main(["check", "--root", str(site_root)]) == 1


def _patch_transport(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    real = cli.check_external

    async def fake(links, **kwargs):  # type: ignore[no-untyped-def]
        transport = httpx.MockTransport(lambda r: httpx.Response(status))
        return await real(links, transport=transport, pause=0)

    monkeypatch.setattr(cli, "check_external", fake)


@pytest.mark.parametrize(("status", "code"), [(200, 0), (404, 1)])
def test_check_external_writes_the_report(
    site_root: Path, monkeypatch: pytest.MonkeyPatch, status: int, code: int
) -> None:
    (site_root / "README.md").write_text("[x](https://a.example/)\n", encoding="utf-8")
    _patch_transport(monkeypatch, status)

    assert cli.main(["check-external", "--root", str(site_root)]) == code
    text = (site_root / cli.REPORT).read_text(encoding="utf-8")
    assert "https://a.example/" in text


def test_check_external_logs_where_a_redirect_went(
    site_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (site_root / "README.md").write_text("[x](https://a.example/)\n", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a.example":
            return httpx.Response(302, headers={"Location": "https://b.example/"})
        return httpx.Response(200)

    real = cli.check_external

    async def fake(links, **kwargs):  # type: ignore[no-untyped-def]
        return await real(links, transport=httpx.MockTransport(handler), pause=0)

    monkeypatch.setattr(cli, "check_external", fake)

    assert cli.main(["check-external", "--root", str(site_root)]) == 1


def test_run_as_a_module(site_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["doc_links", "build", "--root", str(site_root)])
    monkeypatch.delitem(sys.modules, "solidworks_mcp.doc_links.__main__", raising=False)

    with pytest.raises(SystemExit) as exit_:
        runpy.run_module("solidworks_mcp.doc_links", run_name="__main__")

    assert exit_.value.code == 0
