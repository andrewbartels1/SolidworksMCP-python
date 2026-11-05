## Context

See proposal.md for why. Current state:

- `server.py` builds `FastMCP("SolidWorks MCP Server", version=...)` with no
  `instructions` and registers no resources; tools come from
  `tools.register_tools`.
- `cli_main` starts the server, except `solidworks-mcp setup ...`, which hands
  off to the Typer app in `setup/cli.py`.
- FastMCP 3.4.9 (installed) has
  `fastmcp.server.providers.skills.SkillProvider(skill_path)`, which serves
  one skill folder as `skill://<name>/SKILL.md`, `skill://<name>/_manifest`
  and its other files, added with `mcp.add_provider(...)`. The
  `SkillCatalogProvider` and `Skill` classes the user's notes mention are
  FastMCP 4.x and are not used.
- The wheel packages `src/solidworks_mcp`, so files placed under it ship.
- Tool descriptions (#82) already say what each tool does; the skill must
  not repeat them.

## Goals / Non-Goals

**Goals:** one source of guidance, in the package, reachable three ways
(server instructions, `skill://` resources, an installed skill), and a test
that fails when it names a tool that is gone or recommends one that can't
run.

**Non-Goals:**

- Fixing the faults the skill warns about (queue item 10).
- Per-client install logic beyond a skills folder (no editing of client
  configs; `solidworks-mcp setup` stays as it is).
- Contributor guidance: `com-api-pitfalls.md` stays the COM reference.

## Decisions

### The skill lives in the package, at `src/solidworks_mcp/skills/solidworks-mcp/`

Rather than `skills/solidworks-mcp/` at the repo root (the issue's
suggestion). Inside the package it ships in the wheel, so `uvx` and pip
installs can serve and install it without the repo; at the root it would need
extra packaging config and would be missing from installs. The
`skills/` folder name keeps the layout the issue describes.

### Layout: `SKILL.md` plus four reference files

- `SKILL.md`: when to use it, the build order, the unit rule, the
  read-back rule, and a map to the references (target: about 150 lines).
- `references/workflows.md`: part, assembly and drawing walk-throughs as
  tool sequences, with the checks between steps.
- `references/selection-and-units.md`: planes, faces, edges; every input
  that takes metres (`measure_entities`, the `edge_names` point specs of
  `add_fillet`/`add_chamfer`) against the rest in mm.
- `references/errors-and-limits.md`: reading an error (`error_type`,
  `hint`), `rebuild_model` and `undo`, the tools that can't run yet, and
  the known faults from queue item 10 with their workarounds.
- `references/vba-fallback.md`: when to use the VBA generation tools and
  `execute_macro`, and when not to.

This keeps `SKILL.md` short (it is read whole), with detail loaded only when
needed, which is how both Claude Code and the `skill://` manifest are meant
to work.

### Serve it with `SkillProvider`, supporting files as a template

`mcp.add_provider(SkillProvider(path))` in `server.setup()`, with the
default `supporting_files="template"`: `list_resources` shows `SKILL.md` and
the manifest, and the reference files are read through the manifest. This
keeps the resource list short. Alternative, `"resources"` (every file
listed): rejected, it lengthens the list every client loads.

### Instructions: a constant next to the skill, at most 1500 characters

A module constant (`skills.SERVER_INSTRUCTIONS`) passed to `FastMCP(...,
instructions=...)`. It holds only the rules a session can't do without (see
the spec) and points to the skill. Alternative, generating it from
`SKILL.md`: rejected; the two have different jobs and lengths.

### `solidworks-mcp skill install` as its own small Typer app

`cli_main` routes `skill` the way it routes `setup`. The command takes
`--project`, `--dir PATH` and `--dry-run`, and copies the packaged files with
`importlib.resources`, overwriting only files it ships. It never deletes,
never follows the folder outside the target, and reads nothing but the
packaged skill, so it can't touch other users' or tools' files. It needs no
network or token.

Alternatives: an option on `setup` (rejected: `setup` is an interactive flow
about client configs; mixing the two would make `--yes` also write skills),
or only documenting a manual copy (rejected: the issue asks for one
command). `setup` prints a one-line hint about `skill install` at the end;
that is the only change to it.

### A test keeps the skill true

`tests/integration/test_skill_content.py` (it spans the skill, the tools
and the instructions, so it is cross-module) parses tool names from
the skill files and the instructions (backticked names that match the
registered-tool pattern) and checks each is registered, and that no tool the
skill's build steps recommend is one that can't run (the "Not available yet"
sentence in its description). A fault fixed later must also be removed from
`errors-and-limits.md`: the queue's item-10 entry says so.

## Risks / Trade-offs

- [The skill drifts from the tools as they change] → the name test above,
  and the queue note that fixing a fault edits the skill.
- [Clients that ignore `instructions` and resources] → the installed skill
  covers them; the README says how.
- [Codex's skills folder may differ by version] → `--dir` takes any folder;
  the README names Claude Code's folder and shows `--dir` for others rather
  than guessing a path.
- [The measured run depends on live SolidWorks and an agent run] → it is the
  last task, run by the user with `live_demo.ps1`-style permission, and does
  not block merging the skill.

## Migration Plan

Additive. Rollback is removing the provider and instructions line; installed
skills are plain files users can delete.

## Open Questions

- Which demo prompt the measurement uses: the bracket demo (#147, queue item
  6, may be narrowed) or the monitor-stand demo already in `docs/demos/`.
  Either fits the task; it is chosen when the live run is scheduled.
