# Agent Skill

The server ships a skill, `solidworks-mcp`, for agents that use its tools.
Each tool's own description says what that tool does
([Tool Description Standard](tool-description-standard.md)); the skill
covers what spans tools:

- the order to build in: create or open a document, sketch, close the
  sketch, then the feature, and `verify_model` at the end;
- units: inputs are millimetres and degrees, except the few that take metres;
- choosing planes, faces and edges, and reading what the user selected;
- checking results, since a tool's success doesn't prove the geometry;
- reading errors and recovering with `rebuild_model` and `undo`;
- the tools that can't run yet and the known faults, with workarounds;
- when to write VBA instead.

The files are `SKILL.md` and four references in
`src/solidworks_mcp/skills/solidworks-mcp/`, installed with the package.

## Three ways an agent gets it

| Way | What the agent sees | Needs |
| --- | --- | --- |
| Server instructions | A short text in the MCP initialize response: start with `get_model_info`, the build order, the unit rule, `verify_model`, and where the skill is | Nothing; every client that shows instructions gets it |
| MCP resources | `skill://solidworks-mcp/SKILL.md`, a `skill://solidworks-mcp/_manifest` listing its files, and each reference file | A client that reads resources |
| Installed skill | The skill in the agent's skills folder, loaded when relevant | `solidworks-mcp skill install` |

## Installing it

```powershell
uvx solidworks-mcp-python skill install            # ~/.claude/skills/solidworks-mcp
uvx solidworks-mcp-python skill install --project  # .claude/skills in this folder
uvx solidworks-mcp-python skill install --dir C:\path\to\skills  # another agent
uvx solidworks-mcp-python skill install --dry-run  # show, write nothing
```

The command copies the packaged files into `<folder>/solidworks-mcp/`,
replacing older copies of them and leaving any other file there alone. It
reads nothing but the packaged skill (no client config, no other skill) and
needs no network or login. Re-run it after upgrading the server.

## Keeping it true

`tests/integration/test_skill_content.py` fails when the skill or the
instructions name a tool that isn't registered, or send an agent to a tool
that can't run yet (those may be named only in the limits reference, which
lists them). When a fault in `openspec/queue.md` item 10 is fixed, remove
it from `references/errors-and-limits.md` in the same change.

For changing the server's COM code, the contributor reference is
[COM API Pitfalls](com-api-pitfalls.md).
