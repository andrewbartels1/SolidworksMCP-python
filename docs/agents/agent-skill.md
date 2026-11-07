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

## Does it help? Measured on the U-joint

The skill was tested on a hard prompt: rebuild SolidWorks' own U-Joint
sample, eight parts, a crank sub-assembly and a main assembly that must move
as a mechanism, from a plain-English description (see the
[U-joint demo](../demos.md#ujoint)). Claude Code with **Opus 5.5 at medium
effort** ran it in fresh sessions on the same SolidWorks: once with the skill
installed and the server instructions, once without either. Both had the same
tool descriptions.

| | With skill | Without skill |
| --- | --- | --- |
| Time | 23.5 min | 21.9 min |
| SolidWorks tool calls | 294 | 268 |
| SolidWorks errors | 3 | 7 |
| `verify_model` checks | 17 | 8 |
| Output tokens | 451k | 385k |
| Main assembly | 7 parts, rotations left free | 7 parts, 20 mates, motion tested with a temporary 30° mate |

Part volumes (mm³) against the original sample:

| Part | Sample | With skill | Without skill |
| --- | --- | --- | --- |
| bracket | 56,363.5 | 56,922.8 | 56,922.8 |
| Yoke_male | 30,825.7 | 30,777.8 | 30,777.9 |
| Yoke_female | 27,252.8 | 27,210.2 | 27,210.2 |
| spider | 4,775.0 | 4,775.0 | 4,775.0 |
| pin | 2,642.9 | 2,642.9 | 2,642.9 |
| crank-shaft | 5,948.8 | 5,935.5 | 5,935.6 |
| crank-arm | 8,206.4 | 8,206.4 | 8,206.4 |
| crank-knob | 7,528.1 | 7,528.1 | 7,528.1 |

The bracket's extra 1 % is the corner where its lip meets the foot: the
sample's thin feature trims it, and the prompt never described it. The
crank shaft's 0.2 % is its collar fillets, which are larger than the step they
sit on (both sessions said so).

**The takeaway:** for Opus 5.5 at medium effort, this skill changed *how* the
agent worked (fewer errors, twice the checking, about 17 % more tokens), not
*what* it built: both sessions made the same parts. The tool descriptions
already carry what the skill says. A skill earns its tokens only when it adds
what the model can't get from the tools, such as mates that leave a mechanism
free to move, reference-geometry recipes and design-intent checks. We need
new and better skills, and [#207](https://github.com/andrewbartels1/SolidworksMCP-python/issues/207) tracks writing and measuring them.

One run per arm is a single data point. An earlier pair of runs, before the
prompt was corrected, came out the same way. Record the model and effort
level with every measurement.

## Keeping it true

`tests/integration/test_skill_content.py` fails when the skill or the
instructions name a tool that isn't registered, or send an agent to a tool
that can't run yet (those may be named only in the limits reference, which
lists them). When a fault in `openspec/queue.md` (the small-faults list) is fixed, remove
it from `references/errors-and-limits.md` in the same change.

For changing the server's COM code, the contributor reference is
[COM API Pitfalls](com-api-pitfalls.md).
