"""Find every link in the README and the docs, and check it.

- :func:`find_links` reads Markdown (and ``llms.txt``) and returns each
  link with its file and line. Links in fenced or inline code are
  examples, not links, and are left out, as are ``mailto:`` links.
- :func:`check_internal` checks, offline, links to this project's own
  pages and files (relative links, ``site_url`` links and ``blob``/``tree``
  links into this repository), including ``#anchors``.
- :func:`check_external` visits every other URL once and fails a dead
  link or a redirect to a different site (spec ``docs/link-check``).
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

from .pages import Site, heading_ids, source_lines

#: Files outside ``docs/`` that are checked.
EXTRA_FILES = ("README.md",)

_CODE_SPAN = re.compile(r"(`+).+?\1")
_IMAGE = re.compile(r"!\[[^\[\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
_INLINE = re.compile(r"\[[^\[\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")
_REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)")
_ANGLE = re.compile(r"<((?:https?)://[^>\s]+)>")
_HTML_ATTR = re.compile(r"""\b(?:href|src)=["']([^"']+)["']""")
_BARE = re.compile(r"(?<![(<\"'=\[])\bhttps?://[^\s<>()\[\]\"'`]+")


@dataclass(frozen=True)
class Link:
    """One link and where it appears.

    Attributes:
        file: The file it is in, relative to the repository root.
        line: Its line number.
        target: The link as written.
    """

    file: str
    line: int
    target: str


def checked_files(root: Path) -> list[Path]:
    """The README, every Markdown page under ``docs/`` and ``docs/llms.txt``."""
    docs = root / "docs"
    files = [root / name for name in EXTRA_FILES]
    files += sorted(docs.rglob("*.md"))
    llms = docs / "llms.txt"
    if llms.is_file():
        files.append(llms)
    return [f for f in files if f.is_file()]


def find_links(text: str, file: str) -> list[Link]:
    """Every link in a Markdown text, outside code.

    Args:
        text: The file's text.
        file: Its path relative to the repository root.

    Returns:
        The links, in file order.
    """
    found: list[Link] = []
    for number, line, code in source_lines(text):
        if code:
            continue
        plain = _CODE_SPAN.sub(lambda m: " " * len(m.group(0)), line)
        targets: list[str] = []
        ref = _REF_DEF.match(plain)
        if ref:
            targets.append(ref.group(1))
        else:
            # Images first, so a badge (an image inside a link) gives both.
            targets += _IMAGE.findall(plain)
            plain = _IMAGE.sub("IMAGE", plain)
            targets += _INLINE.findall(plain)
            targets += _ANGLE.findall(plain)
            targets += _HTML_ATTR.findall(plain)
            rest = _HTML_ATTR.sub(" ", _ANGLE.sub(" ", _INLINE.sub(" ", plain)))
            targets += [t.rstrip(".,;:!?*_") for t in _BARE.findall(rest)]
        found += [
            Link(file, number, target)
            for target in targets
            if target and not target.lower().startswith("mailto:")
        ]
    return found


def all_links(root: Path) -> list[Link]:
    """Every link in every checked file under ``root``."""
    links: list[Link] = []
    for path in checked_files(root):
        rel = path.relative_to(root).as_posix()
        links += find_links(path.read_text(encoding="utf-8"), rel)
    return links


def is_external(target: str) -> bool:
    """Whether a link names a scheme (``https://...``) rather than a path."""
    return bool(re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Offline


def check_internal(root: Path, site: Site, links: Iterable[Link]) -> list[str]:
    """Problems with links to this project's own pages and files.

    Relative links resolve from the linking file; ``site_url`` links map
    back to ``docs/``; ``<repo_url>/blob|tree/<branch>/<path>`` links map to
    the checkout. Links to other sites are left to :func:`check_external`.

    Args:
        root: The repository root.
        site: The site settings.
        links: The links to check.

    Returns:
        ``file:line: problem`` messages; empty when every link resolves.
    """
    ids: dict[Path, set[str]] = {}
    problems: list[str] = []
    for link in links:
        resolved = _local_target(root, site, link)
        if resolved is None:
            continue
        path, anchor = resolved
        where = f"{link.file}:{link.line}"
        if not path.exists():
            problems.append(
                f"{where}: {link.target}: no such file ({_rel(root, path)})"
            )
            continue
        if path.is_dir():
            path = _index_of(path)
            if path is None:
                continue
        if anchor and path.suffix == ".md":
            if path not in ids:
                ids[path] = heading_ids(path.read_text(encoding="utf-8"))
            if anchor not in ids[path]:
                problems.append(
                    f"{where}: {link.target}: {_rel(root, path)} has no heading "
                    f"or id `{anchor}`"
                )
    return problems


def _rel(root: Path, path: Path) -> str:
    """``path`` relative to ``root`` when it is inside it."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _index_of(directory: Path) -> Path | None:
    """The page a directory link opens: its ``index.md`` or ``README.md``."""
    for name in ("index.md", "README.md"):
        if (directory / name).is_file():
            return directory / name
    return None


def _local_target(root: Path, site: Site, link: Link) -> tuple[Path, str] | None:
    """The file (and anchor) a link points at in the checkout, or ``None``.

    ``None`` means the link isn't this project's to check offline: another
    site, the generated API reference, or a repository page that isn't a
    file (issues, pull requests, actions).
    """
    target = link.target
    if target.startswith(site.url + "/") or target == site.url:
        return _site_target(root, site, target)
    if target.startswith(site.repo_url + "/"):
        return _repo_target(root, site, target)
    if is_external(target):
        return None
    path_part, _, anchor = target.partition("#")
    base = (root / link.file).parent
    if not path_part:
        return root / link.file, anchor
    path_part = unquote(path_part.split("?")[0])
    if path_part.startswith("/"):
        return root / path_part.lstrip("/"), anchor
    if link.file.startswith("docs/") and _is_api(base / path_part, root):
        return None
    return (base / path_part).resolve(), anchor


def _is_api(path: Path, root: Path) -> bool:
    """Whether ``path`` is under the generated ``docs/api/`` reference."""
    rel = _rel(root, path)
    return rel == "docs/api" or rel.startswith("docs/api/")


def _site_target(root: Path, site: Site, url: str) -> tuple[Path, str] | None:
    """A ``site_url`` link mapped back to the page or file in ``docs/``."""
    parts = urlsplit(url)
    rest = unquote(parts.path)[len(urlsplit(site.url).path) :].strip("/")
    docs = root / "docs"
    if rest == "api" or rest.startswith("api/"):
        return None
    if not rest:
        return docs / "index.md", parts.fragment
    for candidate in (docs / rest, docs / f"{rest}.md", docs / rest / "index.md"):
        if candidate.is_file():
            return candidate, parts.fragment
    return docs / rest, parts.fragment


def _repo_target(root: Path, site: Site, url: str) -> tuple[Path, str] | None:
    """A ``<repo_url>/blob|tree/<branch>/<path>`` link mapped to the checkout."""
    parts = urlsplit(url)
    rest = unquote(parts.path)[len(urlsplit(site.repo_url).path) :].strip("/")
    match = re.match(r"^(?:blob|tree)/[^/]+/(.+)$", rest)
    if not match:
        return None
    return root / match.group(1), parts.fragment


# ---------------------------------------------------------------------------
# Online


@dataclass
class Result:
    """What visiting one URL found.

    Attributes:
        url: The URL as written.
        ok: Whether it passed.
        detail: The status, or what went wrong.
        final_url: Where redirects ended, when they moved it.
        where: Every ``file:line`` it appears on.
    """

    url: str
    ok: bool
    detail: str
    final_url: str | None = None
    where: list[str] = field(default_factory=list)


def _host(url: str) -> str:
    """The URL's host, lowercase, without a leading ``www.``."""
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


#: Hosts a site legitimately hands its pages to: GitHub serves release
#: downloads, raw files and avatars from its content hosts.
SAME_SITE: dict[str, tuple[str, ...]] = {
    "github.com": (
        "objects.githubusercontent.com",
        "raw.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "avatars.githubusercontent.com",
    ),
}

#: URLs (by prefix) a script can't check, and why. The report lists each
#: as "not checked" with its reason; nothing is skipped silently.
NOT_CHECKED: dict[str, str] = {
    "https://towardsdatascience.com/": (
        "answers 403 to any script; a reference article, check it by hand"
    ),
    "https://www.solidworks.com/": (
        "never answers a script (times out); the vendor's home page"
    ),
}

_GITHUB_ITEM = re.compile(
    r"^https://github\.com/([\w.-]+)/([\w.-]+)/(?:issues|pull)/(\d+)/?$"
)


def api_probe(url: str) -> str | None:
    """The GitHub API URL that answers for a GitHub issue or pull request page.

    GitHub rate-limits scripts reading its issue pages (HTTP 429) but serves
    its API to them; the issues endpoint answers for pull requests too.

    Args:
        url: A link.

    Returns:
        The API URL, or ``None`` when ``url`` isn't an issue or PR page.
    """
    match = _GITHUB_ITEM.match(url)
    if not match:
        return None
    owner, repo, number = match.groups()
    return f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"


def github_headers(environ: dict[str, str]) -> dict[str, str]:
    """The headers for GitHub API calls: the CI token when one is set.

    Args:
        environ: The environment (``GITHUB_TOKEN`` or ``GH_TOKEN``).

    Returns:
        An ``Authorization`` header, or nothing.
    """
    token = environ.get("GITHUB_TOKEN") or environ.get("GH_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def same_site(url: str, final: str) -> bool:
    """Whether a redirect from ``url`` to ``final`` stays on the same site.

    Args:
        url: The URL as written.
        final: Where its redirects ended.

    Returns:
        True when the hosts match (``www.`` ignored), one is a subdomain of
        the other (``codecov.io`` -> ``app.codecov.io``), or ``final`` is one
        of the hosts :data:`SAME_SITE` lists for ``url``'s host.
    """
    start, end = _host(url), _host(final)
    if start == end or end in SAME_SITE.get(start, ()):
        return True
    return end.endswith("." + start) or start.endswith("." + end)


_RETRY_STATUS = {429, 500, 502, 503, 504}


async def visit(
    client: httpx.AsyncClient,
    url: str,
    *,
    attempts: int = 4,
    pause: float = 2.0,
    sleep: Callable[[float], object] = asyncio.sleep,
    probe: str | None = None,
    headers: dict[str, str] | None = None,
) -> Result:
    """Visit one URL and judge it.

    A GET follows redirects. It passes on a 2xx that ended on the same
    site. Timeouts, dropped connections, 429 and 5xx are retried up to
    ``attempts`` times; any other failure is final at once.

    Args:
        client: The HTTP client (redirects followed).
        url: The URL to visit.
        attempts: How many tries before a retryable failure is final.
        pause: Seconds before the first retry; doubled each time.
        sleep: The pause function (tests pass one that doesn't wait).
        probe: A URL to request instead of ``url`` (see :func:`api_probe`).
        headers: Extra request headers (sent only to ``probe``).

    Returns:
        The result.
    """
    detail = ""
    target = probe or url
    via = " (GitHub API)" if probe else ""
    for attempt in range(attempts):
        if attempt:
            await sleep(pause * 2 ** (attempt - 1))  # type: ignore[misc]
        try:
            response = await client.get(target, headers=headers or {})
        except (
            httpx.TimeoutException,
            httpx.RemoteProtocolError,
            httpx.ReadError,
        ) as error:
            detail = f"{type(error).__name__} (tried {attempt + 1} times)"
            continue
        except httpx.HTTPError as error:
            return Result(url, False, f"{type(error).__name__}: {error}")
        final = str(response.url)
        moved = final if final.rstrip("/") != target.rstrip("/") else None
        if response.status_code in _RETRY_STATUS:
            detail = f"HTTP {response.status_code} (tried {attempt + 1} times)"
            wait = _retry_after(response)
            if wait and attempt + 1 < attempts:
                await sleep(wait)  # type: ignore[misc]
            continue
        if not response.is_success:
            return Result(url, False, f"HTTP {response.status_code}{via}", moved)
        if moved and not same_site(target, final):
            return Result(url, False, "redirects to another site", moved)
        return Result(url, True, f"HTTP {response.status_code}{via}", moved)
    return Result(url, False, detail)


def _retry_after(response: httpx.Response) -> float:
    """Seconds a 429/503 asks to wait (``Retry-After``), at most 60; else 0."""
    value = response.headers.get("retry-after", "")
    return min(float(value), 60.0) if value.isdigit() else 0.0


USER_AGENT = "SolidworksMCP-python docs link check (+https://github.com/andrewbartels1/SolidworksMCP-python)"


async def check_external(
    links: Iterable[Link],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    concurrency: int = 8,
    per_host: int = 2,
    timeout: float = 30.0,
    pause: float = 2.0,
) -> list[Result]:
    """Visit every external URL once, eight at a time.

    Args:
        links: The links; those that aren't ``http(s)`` URLs are skipped.
        transport: An httpx transport (tests pass a mock one).
        concurrency: How many URLs are visited at once.
        per_host: How many at once on one host (GitHub answers 429 to more).
        timeout: Seconds per request.
        pause: Seconds before the first retry.

    Returns:
        One result per unique URL, sorted by URL, each listing where it
        appears.
    """
    where: dict[str, list[str]] = {}
    for link in links:
        if re.match(r"^https?://", link.target, re.IGNORECASE):
            where.setdefault(link.target, []).append(f"{link.file}:{link.line}")
    api_headers = github_headers(dict(os.environ))
    gate = asyncio.Semaphore(concurrency)
    hosts: dict[str, asyncio.Semaphore] = {}
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        transport=transport,
        headers={"User-Agent": USER_AGENT},
    ) as client:

        async def one(url: str) -> Result:
            reason = next(
                (why for prefix, why in NOT_CHECKED.items() if url.startswith(prefix)),
                None,
            )
            if reason is not None:
                return Result(url, True, f"not checked: {reason}", where=where[url])
            probe = api_probe(url)
            host = hosts.setdefault(_host(probe or url), asyncio.Semaphore(per_host))
            async with gate, host:
                result = await visit(
                    client,
                    url,
                    pause=pause,
                    probe=probe,
                    headers=api_headers if probe else None,
                )
            result.where = where[url]
            return result

        results = await asyncio.gather(*(one(url) for url in sorted(where)))
    return list(results)


def report(results: list[Result]) -> str:
    """The Markdown report: a count, then every URL with its result.

    Args:
        results: The results of :func:`check_external`.

    Returns:
        The report's text.
    """
    failed = [r for r in results if not r.ok]
    lines = [
        "# Link report",
        "",
        f"{len(results)} external URLs visited: {len(results) - len(failed)} passed, "
        f"{len(failed)} failed.",
        "",
        "| Result | URL | Went to | Where |",
        "| --- | --- | --- | --- |",
    ]
    for result in sorted(results, key=lambda r: (r.ok, r.url)):
        mark = "pass" if result.ok else "**FAIL**"
        lines.append(
            f"| {mark}: {result.detail} | {result.url} | {result.final_url or ''} | "
            f"{', '.join(result.where)} |"
        )
    return "\n".join(lines) + "\n"
