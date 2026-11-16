"""Finding and checking links (spec: docs/link-check)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from solidworks_mcp.doc_links.links import (
    Link,
    Result,
    all_links,
    api_probe,
    check_external,
    check_internal,
    checked_files,
    find_links,
    github_headers,
    is_external,
    report,
    same_site,
    visit,
)
from solidworks_mcp.doc_links.pages import load_site

from .conftest import REPO, SITE


def _targets(text: str) -> list[str]:
    return [link.target for link in find_links(text, "f.md")]


def test_find_links_of_every_kind() -> None:
    text = (
        '[a](a.md) and ![img](i.png "title") and [b](<b.md>)\n'
        "[![badge](https://img/x.svg)](https://site/y)\n"
        "<https://auto.example/p> and https://bare.example/q.\n"
        '<a href="h.md">h</a> <img src="s.png">\n'
        "[ref]: https://ref.example/r\n"
        "[mail](mailto:me@example.com)\n"
    )

    assert _targets(text) == [
        "i.png",
        "a.md",
        "b.md",
        "https://img/x.svg",
        "https://site/y",
        "https://auto.example/p",
        "https://bare.example/q",
        "h.md",
        "s.png",
        "https://ref.example/r",
    ]


def test_find_links_skips_code() -> None:
    text = "```\n[x](in-fence.md) http://127.0.0.1:1\n```\nUse `http://YOUR-IP:8000` [y](y.md)\n"

    links = find_links(text, "f.md")

    assert links == [Link("f.md", 4, "y.md")]


def test_checked_files_and_all_links(site_root: Path) -> None:
    (site_root / "README.md").write_text("[docs](docs/index.md)\n", encoding="utf-8")
    (site_root / "docs/llms.txt").write_text(f"- [P]({SITE}/): x\n", encoding="utf-8")

    files = [p.relative_to(site_root).as_posix() for p in checked_files(site_root)]
    links = all_links(site_root)

    assert files == [
        "README.md",
        "docs/guide/more.md",
        "docs/guide/start.md",
        "docs/index.md",
        "docs/llms.txt",
    ]
    assert Link("docs/llms.txt", 1, f"{SITE}/") in links
    assert Link("README.md", 1, "docs/index.md") in links


@pytest.mark.parametrize(
    ("target", "external"),
    [("https://x", True), ("mailto:x", True), ("a.md", False), ("#a", False)],
)
def test_is_external(target: str, external: bool) -> None:
    assert is_external(target) is external


def _problems(root: Path, file: str, *targets: str) -> list[str]:
    links = [Link(file, n, t) for n, t in enumerate(targets, start=1)]
    return check_internal(root, load_site(root), links)


def test_check_internal_passes_good_links(site_root: Path) -> None:
    (site_root / "docs/img.png").write_bytes(b"x")
    (site_root / "src.py").write_text("", encoding="utf-8")
    (site_root / "docs/sub").mkdir()
    (site_root / "docs/sub/index.md").write_text("# Sub\n", encoding="utf-8")
    (site_root / "docs/empty").mkdir()

    assert (
        _problems(
            site_root,
            "docs/guide/start.md",
            "more.md#details_1",
            "#top",
            "#details",
            "../img.png",
            "../sub/",
            "../sub/#sub",
            "../empty/#x",
            "../api/solidworks_mcp/",
            "/src.py",
            "more.md?plain=1",
            "https://other.example/",
            f"{SITE}",
            f"{SITE}/guide/more/#details",
            f"{SITE}/img.png",
            f"{SITE}/api/x/",
            f"{REPO}/blob/main/src.py",
            f"{REPO}/issues/1",
        )
        == []
    )


def test_check_internal_reports_missing_files_and_anchors(site_root: Path) -> None:
    problems = _problems(
        site_root,
        "docs/guide/start.md",
        "gone.md",
        "more.md#nope",
        f"{SITE}/guide/gone/",
        f"{REPO}/tree/main/nope",
    )

    assert problems == [
        "docs/guide/start.md:1: gone.md: no such file (docs/guide/gone.md)",
        "docs/guide/start.md:2: more.md#nope: docs/guide/more.md has no heading or id `nope`",
        f"docs/guide/start.md:3: {SITE}/guide/gone/: no such file (docs/guide/gone)",
        f"docs/guide/start.md:4: {REPO}/tree/main/nope: no such file (nope)",
    ]


def test_check_internal_names_a_path_outside_the_root(site_root: Path) -> None:
    (problem,) = _problems(site_root, "docs/index.md", "../../outside-nowhere.md")

    assert "no such file" in problem and "outside-nowhere.md" in problem


def test_check_internal_resolves_readme_links_from_the_root(site_root: Path) -> None:
    assert _problems(site_root, "README.md", "docs/index.md#proj", "docs/") == []


@pytest.mark.parametrize(
    ("url", "final", "same"),
    [
        ("https://www.a.com/x", "https://a.com/y", True),
        ("https://codecov.io/gh", "https://app.codecov.io/gh", True),
        ("https://app.b.io/", "https://b.io/", True),
        (
            "https://github.com/o/r/releases/download/x",
            "https://objects.githubusercontent.com/z",
            True,
        ),
        ("https://andrewbartels1.github.io/p/", "https://andrewbartels1.com/p/", False),
        ("https://a.com/", "https://parked.example/", False),
        ("https://notcodecov.io/", "https://codecov.io/", False),
    ],
)
def test_same_site(url: str, final: str, same: bool) -> None:
    assert same_site(url, final) is same


def test_api_probe_and_headers() -> None:
    assert (
        api_probe(f"{REPO}/issues/12")
        == "https://api.github.com/repos/owner/proj/issues/12"
    )
    assert (
        api_probe(f"{REPO}/pull/3/")
        == "https://api.github.com/repos/owner/proj/issues/3"
    )
    assert api_probe(f"{REPO}/blob/main/x") is None
    assert github_headers({"GH_TOKEN": "t"}) == {"Authorization": "Bearer t"}
    assert github_headers({}) == {}


async def _no_wait(_seconds: float) -> None:
    return None


def _client(handler) -> httpx.AsyncClient:  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )


def _visit(handler, url: str, **kwargs) -> Result:  # type: ignore[no-untyped-def]
    async def run() -> Result:
        async with _client(handler) as client:
            return await visit(client, url, sleep=_no_wait, **kwargs)

    return asyncio.run(run())


def test_visit_passes_a_200() -> None:
    result = _visit(lambda r: httpx.Response(200), "https://a.com/")

    assert (result.ok, result.detail, result.final_url) == (True, "HTTP 200", None)


def test_visit_fails_a_404_at_once() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(404)

    result = _visit(handler, "https://a.com/x")

    assert (result.ok, result.detail, len(calls)) == (False, "HTTP 404", 1)


def test_visit_fails_a_host_that_does_not_resolve() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("name resolution failed", request=request)

    result = _visit(handler, "https://gone.example/")

    assert not result.ok
    assert result.detail == "ConnectError: name resolution failed"


def test_visit_retries_a_timeout_then_passes() -> None:
    tries = iter([True, False])

    def handler(request: httpx.Request) -> httpx.Response:
        if next(tries):
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200)

    assert _visit(handler, "https://a.com/").ok


def test_visit_gives_up_after_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    result = _visit(handler, "https://a.com/", attempts=2)

    assert (result.ok, result.detail) == (False, "ConnectTimeout (tried 2 times)")


def test_visit_honours_retry_after_on_429() -> None:
    waits: list[float] = []

    async def record(seconds: float) -> None:
        waits.append(seconds)

    responses = iter(
        [httpx.Response(429, headers={"Retry-After": "120"}), httpx.Response(503)]
    )

    async def run() -> Result:
        async with _client(lambda r: next(responses)) as client:
            return await visit(
                client, "https://a.com/", attempts=2, pause=1, sleep=record
            )

    result = asyncio.run(run())

    assert (result.ok, result.detail) == (False, "HTTP 503 (tried 2 times)")
    assert waits == [60.0, 1]


def _redirecting(to: str):  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a.com" and request.url.path == "/":
            return httpx.Response(301, headers={"Location": to})
        return httpx.Response(200)

    return handler


def test_visit_fails_a_redirect_to_another_site() -> None:
    result = _visit(_redirecting("https://parked.example/"), "https://a.com/")

    assert (result.ok, result.detail, result.final_url) == (
        False,
        "redirects to another site",
        "https://parked.example/",
    )


def test_visit_passes_a_same_site_redirect_and_shows_it() -> None:
    result = _visit(_redirecting("https://a.com/en/"), "https://a.com/")

    assert (result.ok, result.final_url) == (True, "https://a.com/en/")


def test_visit_uses_the_probe_and_its_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(410)

    result = _visit(
        handler,
        f"{REPO}/issues/1",
        probe="https://api.github.com/repos/owner/proj/issues/1",
        headers={"Authorization": "Bearer t"},
    )

    assert (result.ok, result.detail) == (False, "HTTP 410 (GitHub API)")
    assert seen[0].url.host == "api.github.com"
    assert seen[0].headers["Authorization"] == "Bearer t"


def test_check_external_visits_each_url_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "api.github.com":
            assert request.headers["Authorization"] == "Bearer tok"
        else:
            assert "Authorization" not in request.headers
        return httpx.Response(200)

    links = [
        Link("a.md", 1, "https://a.com/"),
        Link("b.md", 2, "https://a.com/"),
        Link("a.md", 3, "relative.md"),
        Link("a.md", 4, "https://towardsdatascience.com/article/"),
        Link("a.md", 5, f"{REPO}/issues/7"),
    ]

    results = asyncio.run(
        check_external(links, transport=httpx.MockTransport(handler), pause=0)
    )

    assert sorted(seen) == [
        "https://a.com/",
        "https://api.github.com/repos/owner/proj/issues/7",
    ]
    by_url = {r.url: r for r in results}
    assert by_url["https://a.com/"].where == ["a.md:1", "b.md:2"]
    assert by_url["https://towardsdatascience.com/article/"].detail.startswith(
        "not checked: "
    )
    assert by_url[f"{REPO}/issues/7"].detail == "HTTP 200 (GitHub API)"


def test_report_lists_every_url_failures_first() -> None:
    results = [
        Result("https://ok.example/", True, "HTTP 200", None, ["a.md:1"]),
        Result("https://bad.example/", False, "HTTP 404", None, ["b.md:2", "c.md:3"]),
        Result(
            "https://moved.example/",
            True,
            "HTTP 200",
            "https://moved.example/en/",
            ["d.md:4"],
        ),
    ]

    text = report(results)

    assert "3 external URLs visited: 2 passed, 1 failed." in text
    rows = [
        line for line in text.splitlines() if line.startswith("| ") and "://" in line
    ]
    assert (
        rows[0] == "| **FAIL**: HTTP 404 | https://bad.example/ |  | b.md:2, c.md:3 |"
    )
    assert rows[1].endswith("| https://moved.example/en/ | d.md:4 |")
    assert len(rows) == 3
