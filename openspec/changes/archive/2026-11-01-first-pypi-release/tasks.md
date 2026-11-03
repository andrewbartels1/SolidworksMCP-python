## 1. Setup from uvx

- [x] 1.1 `setup/launcher.py`: detect a uv cache environment from `sys.prefix`; return `uvx` (beside `UV`, else on `PATH`) by absolute path with `["solidworks-mcp-python", *flags]`; fall back to the cached launcher with a warning when `uvx` isn't found
- [x] 1.2 Tests in `tests/solidworks_mcp/setup/test_launcher.py`: uvx cache env, `uv tool` env, `.venv`, `uvx` not found, mock flag
- [x] 1.3 Setup prints the warning when it fell back (`setup/cli.py`), with a test

## 2. Package

- [x] 2.1 `server.py` `cli`: `\f` before the Args section so `--help` is one line per option; test that help has no `typer.Option` text
- [x] 2.2 `pyproject.toml`: `hatch-fancy-pypi-readme` hook with the image and link substitutions; `readme` moves to the hook
- [x] 2.3 A test that builds the metadata description and checks the rewritten GIF URL, an untouched absolute URL and anchor, and the `mcp-name` marker
- [x] 2.4 Version 1.5.0 in `pyproject.toml`, `version.py`, `server.json`; `[1.5.0] - <date>` CHANGELOG section from Unreleased

## 3. Docs

- [x] 3.1 README: badge "tested on 2026"; Install = install uv + `uvx solidworks-mcp-python setup`; every client config runs `uvx solidworks-mcp-python`; link to install-from-source
- [x] 3.2 `README.es-ES.md`: same badge and commands
- [x] 3.3 `docs/getting-started/installation.md`: uvx path first, "Install from source" with `install.ps1`, Troubleshooting entry for a client that can't find `uvx`
- [x] 3.4 `.github/workflows/deploy-docs.yml`: PR builds in their own concurrency group (#194)

## 4. Verify

- [x] 4.1 ruff, the non-live suite at 100% coverage, strict docs build
- [x] 4.2 `uv build`; `twine check`; `uvx --isolated --from <wheel> solidworks-mcp-python --help`; `uvx --from <wheel> solidworks-mcp-python setup --dry-run --yes --mock` shows `uvx` entries
- [x] 4.3 `mcp-publisher validate` (or the schema) passes for `server.json`

## 5. Release (maintainer)

- [x] 5.1 PR closing #194 and part of #172; merge
- [x] 5.2 One-time: PyPI pending trusted publisher (project `solidworks-mcp-python`, repo `andrewbartels1/SolidworksMCP-python`, workflow `release.yml`, environment `pypi`); GitHub environment `pypi`
- [x] 5.3 Tag `v1.5.0` on main and push; check PyPI, the GitHub Release and the registry entry; then close #172
