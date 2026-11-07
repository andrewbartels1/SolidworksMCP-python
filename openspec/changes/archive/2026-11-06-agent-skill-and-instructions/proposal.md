## Why

Agents call this server's tools without knowing how SolidWorks work goes:
that a feature needs a sketch closed first, which tools take millimetres and
which take metres, that a modelling tool's success does not prove the
geometry is right, or which tools can't run yet. The guidance that exists
(`docs/agents/com-api-pitfalls.md`, `.claude/skills/`) is written for
contributors changing the COM code, not for people using the server, and an
agent only sees it if someone pastes it in. Issue #175 asks for a skill users
install into their agent; the tool descriptions (#82, now done) cover each
tool, so what is missing is the guidance that spans tools.

## What Changes

- **A usage skill** for agents that drive the server: `SKILL.md` plus a few
  reference files, shipped inside the Python package so every install has
  it. It covers the build order (part, sketch, `exit_sketch`, feature,
  `verify_model`), units (mm in, with the named exceptions that take metres),
  planes and face/edge selection, reading back after every change, recovering
  from errors (`rebuild_model`, `undo`), the tools that can't run yet and the
  known faults, and when to fall back to VBA generation. Sourced from the
  tool code, the description standard, `com-api-pitfalls.md` and
  `openspec/queue.md`.
- **The server serves the skill** as MCP resources (`skill://solidworks-mcp/SKILL.md`
  and its files), so a client that reads resources gets it with no install.
- **Server instructions**: a short `instructions` text sent at connection
  with the few rules every session needs, pointing to the skill for the rest.
- **One-command install**: `solidworks-mcp skill install` copies the skill
  into an agent's skills folder (Claude Code's user or project folder by
  default, or any folder given). It writes only its own folder and reads no
  other file.
- **README and docs**: the install command and what the skill covers.
- **Measured**: the demo prompt run with and without the skill on real
  SolidWorks, and the difference recorded (live run, with the user's
  permission).

No adapter or COM code changes. Nothing is removed.

## Capabilities

### New Capabilities

- `agents/usage-skill`: the skill's content and the rules that keep it true
  (every tool it names exists and is described as the tool behaves), how the
  server serves it, and how `solidworks-mcp skill install` places it.
- `agents/server-instructions`: the `instructions` text the server sends at
  connection.

### Modified Capabilities

None.

## Impact

- New: `src/solidworks_mcp/skills/solidworks-mcp/` (the skill files),
  `src/solidworks_mcp/skills/` code to serve and install it, a `skill`
  subcommand in `cli_main` (`server.py`).
- Changed: `server.py` passes `instructions` to `FastMCP` and adds the
  skill provider; README and `docs/` gain the install section.
- Packaging: the skill files ship in the wheel (they live under
  `src/solidworks_mcp`, which the wheel already includes).
- Depends on FastMCP 3.4.9's `SkillProvider`, already installed; no new
  dependency.
- No change to `pywin32_adapter.py`, `base.py` or `mock_adapter.py`.
- GitHub issue: #175.
