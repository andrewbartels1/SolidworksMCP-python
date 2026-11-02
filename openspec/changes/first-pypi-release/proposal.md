## Why

Installing the server today means cloning the repo, building a `.venv` and
running `install.ps1`. Nothing is on PyPI and there are no GitHub Releases,
so the `uvx` one-liner that MCP directories and the official MCP Registry
expect doesn't exist (#172). The release workflow and `server.json` are
already in the repo; no version has ever been tagged.

Trying a first release locally turned up four things that would go wrong
on day one:

- `uvx solidworks-mcp-python setup` would write the launcher's path inside
  uv's cache (`%LOCALAPPDATA%\uv\cache\archive-v0\<hash>\...`) into every
  client config. That folder is temporary, so the clients break the next
  time the cache is cleaned.
- The README's GIFs and its links to other files are relative paths, which
  show as broken images and dead links on the PyPI project page.
- `solidworks-mcp-python --help` prints a garbled docstring
  ("Defaults to typer.Option(  None, ...").
- The README badge says SolidWorks 2019–2026; only 2026 has been tested.

Bundled because it is a one-line release blocker of the same kind: pull
request docs builds share a concurrency group with `main` deploys, so a
merge can silently skip the docs deploy (#194).

## What Changes

- **Setup run through `uvx` writes a lasting entry.** When setup runs from
  a uv cache environment, each client entry runs `uvx solidworks-mcp-python`
  (the `uvx` launcher by absolute path) instead of the cached executable.
  Entries written from a `.venv` or a `uv tool install` are unchanged.
- **The install section leads with `uvx`.** The README's Install section
  becomes: install uv, then `uvx solidworks-mcp-python setup`. Every
  per-client config in the README runs `uvx solidworks-mcp-python`, with no
  local paths. Installing from a clone (`install.ps1`) moves to the docs
  Installation page, for contributors.
- **The PyPI page renders.** The package description rewrites the README's
  relative image and file links to absolute GitHub URLs at build time; the
  README in the repo is unchanged.
- **Clean `--help`.** The server CLI's help shows one line per option.
- **Honest version badge.** "Tested on SolidWorks 2026"; other versions are
  described as untested in the README, not claimed.
- **Docs deploys are no longer skipped** by pull-request builds (#194).
- **Version 1.5.0** in `pyproject.toml`, `version.py`, `server.json` and a
  `[1.5.0]` CHANGELOG section, so the tag passes the workflow's version check.
- The `solidworks-mcp` console script stays as an alias, because entries
  written by earlier setups run it. Docs only ever say
  `solidworks-mcp-python`, which is the PyPI name; `uvx solidworks-mcp`
  installs a different project.

Not in this change: the API lookup fix (#195), and the publishing itself.
Tagging `v1.5.0`, and the one-time PyPI trusted-publisher and GitHub
`pypi` environment settings, are done by the maintainer after merge.

## Capabilities

### New Capabilities
- `release/package-publishing`: what a tagged release publishes, and what
  the PyPI package page and `uvx` launch must look like.

### Modified Capabilities
- `setup/client-setup`: "The entry launches the installed server" gains the
  `uvx` case.
- `docs/readme-install`: "One install path" becomes the `uvx` path, and
  every client config launches `uvx solidworks-mcp-python`.

## Impact

- `src/solidworks_mcp/setup/launcher.py` (uv cache detection) and its tests.
- `src/solidworks_mcp/server.py` (`cli` docstring only).
- `pyproject.toml` (version, `hatch-fancy-pypi-readme` build hook),
  `src/solidworks_mcp/version.py`, `server.json`, `CHANGELOG.md`.
- `README.md`, `README.es-ES.md` (badge, install, client configs),
  `docs/getting-started/installation.md` (install from source).
- `.github/workflows/deploy-docs.yml` (concurrency group).
- No COM or adapter code is touched.
