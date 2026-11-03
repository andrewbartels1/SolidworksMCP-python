## Context

See proposal.md for why. What exists:

- `.github/workflows/release.yml` runs on a `v*` tag. It checks that the
  versions match, builds, publishes to PyPI with trusted publishing (the
  `pypi` environment), creates a GitHub Release from the CHANGELOG section,
  and publishes `server.json` with `mcp-publisher` over GitHub OIDC.
- `server.json` names `io.github.andrewbartels1/solidworks-mcp-python`, a
  `pypi` package, `runtimeHint: uvx`. The README carries the `mcp-name`
  marker the registry checks against the PyPI description.
- `setup/launcher.py` `server_command()` returns the `solidworks-mcp`
  script beside `sys.executable`.

Seen locally, 2026-11-01: `uv build` gives a 0.5 MB wheel, and
`uvx --from <wheel> solidworks-mcp-python --help` runs. Inside that uvx
environment, `sys.prefix` is
`%LOCALAPPDATA%\uv\cache\archive-v0\<hash>`, and `UV` is set to the uv
executable.

## Goals / Non-Goals

**Goals:** a first release can be tagged straight after merge, and every
path a user is told to take works after the release.

**Non-Goals:**
- Running the release itself: the tag and the PyPI and GitHub settings
  belong to the maintainer.
- Removing the `solidworks-mcp` script alias.
- A Spanish rewrite of the install section beyond the badge and the
  commands themselves.

## Decisions

**Detect a uvx environment from the path, not from `UV`.** An environment is
temporary when a part of `sys.prefix` matches `archive-v<digits>` and an
ancestor folder is named `cache`. `UV` is also set by `uv run` inside a
project `.venv`, where the `.venv` launcher is the right answer, so it
can't tell the two apart. `uv tool install` puts tools under
`%APPDATA%\uv\tools\`, which is persistent, so the normal path applies.

**Find `uvx` beside `UV`, then on `PATH`.** `uvx.exe` ships next to
`uv.exe`. If neither finds it, fall back to the current behaviour (the
cached launcher) and print a warning that the entry will break when the
cache is cleaned. Setup never writes a bare `uvx` without an absolute path,
because Claude Desktop starts servers with a PATH that may not include
`~\.local\bin`.

*Rejected: always write `uvx solidworks-mcp-python@latest`.* That checks
PyPI on every client start: slower, and it fails offline.

**Rewrite README links at build time with `hatch-fancy-pypi-readme`.** Two
regex substitutions: image sources (`src="docs/...` and `![...](docs/...)`)
go to `raw.githubusercontent.com/.../main/`, and other relative links go to
`github.com/.../blob/main/`. Anchors (`#...`) and absolute URLs are left
alone.

*Rejected: absolute URLs in the README itself.* The GitHub page and local
previews would then show `main` instead of the checked-out branch, and
every new image would need the long form.

**Pull request docs builds get their own concurrency group** (#194):
`pages-pr-<number>`, with `cancel-in-progress` for PRs only. `main` keeps
`pages` and never cancels.

**The `--help` fix uses Click's `\f` marker** at the top of the `cli`
docstring's Args section, so Typer shows only the summary plus each
option's `help`. The docstring keeps its Args section for the API docs.

## Risks / Trade-offs

- [The README points at PyPI before the package exists] → tag `v1.5.0`
  right after merge. The window is the length of one release workflow run.
- [Claude Desktop can't find `uvx` in a hand-written config] → the
  Troubleshooting section says to use the full path from
  `(Get-Command uvx).Source`; setup always writes the full path.
- [A local `uvx --from <wheel>` run makes setup write
  `uvx solidworks-mcp-python`, which resolves to PyPI's latest] →
  acceptable: that is the published package, and the message names it.
- [PyPI trusted publishing isn't configured] → the `publish-pypi` job
  fails and nothing later runs. The tasks list the one-time settings.

## Migration Plan

Existing `.venv` and `install.ps1` users are unaffected; their entries
keep running `solidworks-mcp.exe`. After the release they can switch with
`uvx solidworks-mcp-python setup`, which replaces the `solidworks` entry and
names the launcher it replaced.
