# SolidWorks CAD Assistant & MCP Server

<!-- mcp-name: io.github.andrewbartels1/solidworks-mcp-python -->

**Languages:** [English](README.md) | [Español](README.es-ES.md)

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Windows](https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows)](https://www.microsoft.com/windows)
[![SolidWorks](https://img.shields.io/badge/tested%20on-SolidWorks%202026-red)](https://www.solidworks.com/)
[![Coverage](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python/branch/main/graph/badge.svg)](https://codecov.io/gh/andrewbartels1/SolidworksMCP-python)

Python MCP server for SolidWorks automation with 155 tools, plus an optional agent/prompt-testing layer for AI-assisted workflows.

## See it work

### A whole mechanism from a description

I took SolidWorks' own U-Joint sample, read every part, sketch, feature and mate, and wrote it up as a plain-English prompt: eight parts, a crank sub-assembly, and a main assembly that has to move like a real joint. Then Claude Code (Opus 5.5, medium effort) built it from that prompt alone.

<details>
<summary><b>Prompt</b></summary>

> I want to build a small hand-cranked universal joint in SolidWorks: eight parts, a crank sub-assembly, and the main assembly. It's a mechanism: turning the knob turns the crank, which drives the joint through an angle, so the assemblies must still move the way described in sections 9 and 10. Please reason through each part before you start drawing, check every part once it's built, and tell me if something can't be done with the tools rather than guessing. All sizes are in millimetres (the original was drawn in inches, so the numbers are odd). SolidWorks' Y axis is up. Save every part and both assemblies in this folder, with the names given below.
>
> **1. bracket.SLDPRT: a bent plate, 6.35 mm thick and 38.1 mm wide.**
> Seen from the side (sketch on the Right plane, Y up, Z towards the front), the inside outline of the bend is an open chain:
> - a back wall going straight up 82.55 mm from the origin;
> - from its top, a top arm going forward 57.15 mm;
> - from the origin, a bottom foot going forward 44.45 mm;
> - from the front of the foot, a lip rising at 40° for 42.77 mm (it ends 27.49 mm up and 77.22 mm forward).
> The 6.35 mm thickness is on the outside of that outline: above the top arm, behind the back wall and under the foot. The 38.1 mm width is centred on the Right plane. Drill a 12.7 mm hole straight down through the top arm and on through the foot below it (one cut, both plates), centred across the width and 38.1 mm forward of the back wall's inside face.
>
> **2. Yoke_male.SLDPRT: a fork with a stub shaft.**
> - Start with a 38.1 mm diameter cylinder, 47.625 mm tall, standing on the Top plane.
> - Its bottom becomes a fork with two ears. Each ear is 19.05 mm wide and 8.89 mm thick, and the gap between them is 20.32 mm, centred. Each ear has a rounded end: a full radius of 9.525 mm, centred 9.525 mm above the bottom. Where an ear meets the solid part of the cylinder, round the shoulder with a 9.525 mm radius, so the solid part starts 29.21 mm above the bottom.
> - Drill a 9.525 mm cross hole through both ears at the centre of their rounded ends, square to the ears.
> - On top, add a 12.7 mm diameter stub, 19.05 mm tall, on the cylinder's axis. Chamfer its top edge 1.27 mm at 60°.
> - Cut a flat on the stub, 12.7 mm long down from its top. The flat is 4.7625 mm from the axis, so it is 1.5875 mm deep.
>
> **3. Yoke_female.SLDPRT:** the same 38.1 x 47.625 mm cylinder with the same fork and the same cross hole as the male yoke, but no stub. Instead, a 9.525 mm hole goes all the way through along its axis.
>
> **4. spider.SLDPRT:** a 19.05 mm cube centred on the origin. It has two 9.525 mm holes, both through its centre: one front to back, and one left to right.
>
> **5. pin.SLDPRT:** a 9.398 mm diameter rod, 38.1 mm long.
>
> **6. crank-shaft.SLDPRT: a 12.573 mm diameter shaft, 40 mm long, standing on the Top plane.**
> - Around its bottom 15.875 mm, a collar 18.923 mm in diameter.
> - A 4.763 mm fillet where the collar meets the shaft, and a 4.763 mm fillet on the collar's top outer edge.
> - In the bottom, a D-shaped socket 12.7 mm deep. It is a 12.954 mm circle with a flat 4.889 mm from the axis, to take the male yoke's stub.
> - A 2.381 mm cross hole through the collar wall, square to the socket's flat and 6.35 mm up from the bottom.
> - At the top, a matching flat 6.35 mm long, 4.889 mm from the axis.
> - A 0.794 mm x 45° chamfer on the top end.
>
> **7. crank-arm.SLDPRT: a flat bar, 75 x 19.05 x 6.35 mm.**
> - Near one end, a 12.7 mm D-hole centred 9.525 mm from the end and on the bar's centreline. Its flat is 4.889 mm from the hole's centre, towards that end. It fits the shaft's top flat.
> - Near the other end, a 4.763 mm hole 9.525 mm from that end, also on the centreline.
>
> **8. crank-knob.SLDPRT: a mushroom-shaped knob, revolved 360° about the vertical axis.** Going up from the bottom, its profile has:
> - a 4.572 mm diameter shank, 6.35 mm long;
> - a step out to a 9.525 mm diameter;
> - a concave quarter-round of radius 6.35 mm that flares out to 22.225 mm diameter, 12.7 mm up;
> - a convex half-round of radius 4.7625 mm that reaches 31.75 mm diameter at its widest;
> - a flat top 22.225 mm in diameter, 22.225 mm above the bottom.
>
> **9. crank sub.SLDASM:**
> - The crank shaft is fixed.
> - The crank arm's D-hole goes on the shaft's top flat: the hole is concentric with the shaft, the flats are parallel, and the arm sits on the shoulder where the flat starts. The flats lock the arm to the shaft, so they turn together.
> - The knob's shank goes into the arm's small hole, with the knob's step resting on the arm's top face. The knob stays free to spin in its hole, like a handle.
>
> **10. UJoint.SLDASM:**
> - The bracket is fixed.
> - The male yoke hangs under the bracket's top arm. Its stub goes up through the bracket's hole (concentric), and the top of its cylinder is flat against the underside of the arm. It must stay free to turn in that hole.
> - The spider sits centred between the male yoke's ears, with one of its holes lined up with the ears' cross hole. It pivots on that axis.
> - The female yoke's ears go around the spider's other hole, centred on the spider. Its top face is parallel to the bracket's sloped lip, so its axis points down and forward. It pivots on the spider and turns about its own axis.
> - Put one pin through the male yoke's ears and the spider, and one pin through the female yoke's ears and the spider. Each pin's ends are flush with its yoke's round outside, and each pin turns with its yoke.
> - Insert the crank sub-assembly. Its shaft's D-socket goes over the male yoke's stub: concentric, with the flats parallel, and the bottom of the shaft 1 mm above the top of the bracket. The flats lock the crank to the male yoke.
> - The result should be a mechanism with one free motion: turning the knob around the crank shaft's axis turns the male yoke, the spider rocks on its pins, and the female yoke turns about its tilted axis. Choose mates that leave exactly those rotations free and lock everything else.
>
> When it's all built, check each part's size and the assembly's component and mate counts, say which rotations your mates leave free, and tell me what you couldn't do.

</details>

![The original U-Joint sample beside the agent's build: the same bracket, yokes, spider, pins, crank and knob, in the same pose](docs/assets/demos/ujoint/ujoint_original_vs_agent.jpg)

![The agent's 294 tool calls replayed in SolidWorks: eight parts sketched and cut, then the crank sub-assembly and the U-joint mated together](docs/assets/demos/ujoint/test_ujoint_from_prompt_to_assembly-motion.gif)

Six of the eight parts match the sample's volume within 0.2 %, and all eight within 1 %. The mates leave the mechanism free to turn. The recording replays the session's 294 calls (sped up 80 times). The [walkthrough](https://andrewbartels1.github.io/SolidworksMCP-python/demos/#ujoint) has the prompt, the part-by-part comparison, and what the agent couldn't do. The same prompt run with and without the [agent skill](https://andrewbartels1.github.io/SolidworksMCP-python/agents/agent-skill/) made the same parts, which is why I want skills that improve results (#207).

### A drawing package from one prompt

> Make a 100 x 50 x 10 mm AISI 1020 mounting plate with four M5 clearance holes, 10 mm in from each edge, and draw it fully dimensioned. Stack two of them 10 mm apart, check the result, and draw the assembly with a BOM.

![A fully dimensioned plate, its drawing with GD&T, two plates mated 10 mm apart and the assembly drawing with a BOM, built in SolidWorks through the MCP tools](docs/assets/demos/readme/test_plate_stack_from_prompt_to_drawing-motion.gif)

The 58 tool calls an agent made from that prompt, run against SolidWorks 2026 through the same MCP tools a client calls, and recorded (sped up five times). Each result is checked against a hand calculation: the plate's volume and mass, the 10 mm gap and the BOM quantity. This is a replay of the calls, not a recorded model session.

> **Note:** the demo is not perfect, and is not the most efficient way to get this result. The run pauses after each call so it can be read, and the calls are chosen to show what the tools can do: every sketch dimension is added one at a time, and the mate distance is stepped down only so the plates are seen coming together.

The [walkthrough in the docs](https://andrewbartels1.github.io/SolidworksMCP-python/demos/#prompt-to-drawing) has the agent's plan and every call with its arguments. Run it yourself with the [README demo](tests/live/test_live_sw_readme_demo.py); the calls are also in [`plate_stack_calls.json`](docs/assets/demos/readme/plate_stack_calls.json).

<details>
<summary>The 58 tool calls</summary>

1. **Sketch** (24 calls): `create_sketch` on Top; four `add_line` for the 100 x 50 outline; `add_circle` for each Ø5.5 hole; `add_sketch_dimension` for the 100, the 50, one Ø5.5 and each hole 10 mm from two edges; `add_sketch_constraint` making the other three holes equal; `exit_sketch`
2. **Check and extrude**: `check_sketch_fully_defined`, `create_extrusion` 10 mm (+49 049.7 mm³ read back)
3. **Material and check**: `list_model_dimensions` (finds the Ø5.5 by value), `set_material` AISI 1020, `verify_model` (volume, mass 0.3875 kg, size, 1 feature, 1 body)
4. **Plate drawing**: `generate_drawing_package` PS-01 (A3, four views, every model dimension laid out with no overlaps, notes, title block, PDF), `auto_center_marks`
5. **GD&T**: `add_datum_tag` A, B and C, then `add_gtol` ⊕ Ø0.2 Ⓜ A|B|C on the Ø5.5
6. **Assembly**: `insert_component` twice, `list_components`, `add_mate` Front and Right coincident and Top planes 60 mm apart, `set_dimension` stepping that distance down to 20 mm (10 calls), `verify_model` (2 parts, 3 mates, no interference; the stack measures 30 mm, so the gap is 10 mm)
7. **Assembly drawing**: `set_custom_property` Material, `generate_drawing_package` PS-02 with `include_bom` (the BOM above the isometric: Demo Plate, QTY 2), then the same datums and position frame

</details>

## Overview

> **Tried it?** Tell us what worked and what didn't in a [feedback issue](https://github.com/andrewbartels1/SolidworksMCP-python/issues/new?template=feedback.yml). Reports from real setups decide what gets fixed next.

This project focuses on practical SolidWorks automation with an AI-friendly loop:

1. describe intent
2. generate a plan
3. execute MCP tools
4. inspect results
5. iterate

It includes:

- core MCP runtime for SolidWorks tool execution
- COM/VBA routing and adapter safety wrappers
- tool coverage across modeling, sketching, drawing, analysis, export, automation, templates, and macros
- optional agent orchestration/testing utilities under `src/solidworks_mcp/agents/`

## Demos

Each GIF is a live test driving SolidWorks 2026 through the MCP tools, with the call and its result captioned beneath. Click one to see what it checks, a prompt that asks for it, and its tool calls.

<table>
<tr>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#monitor-stand"><img src="docs/assets/demos/monitor-stand/test_monitor_stand_from_prompt_to_part-motion.gif" alt="A 3D-printable monitor stand from a prompt" width="100%"><img src="docs/assets/demos/monitor-stand/monitor_stand_printing.gif" alt="The monitor stand being 3D printed" width="100%"></a><br><sub>A 3D-printable monitor stand from a prompt, then printed</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#verify-block"><img src="docs/assets/demos/verify-model/test_verify_model_passes_a_block_and_names_what_is_wrong.gif" alt="verify_model passes a block and names what is wrong" width="100%"></a><br><sub><code>verify_model</code> passes a block and names what is wrong</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#verify-assembly"><img src="docs/assets/demos/verify-model/test_assembly_counts_components_mates_and_interference.gif" alt="An assembly: parts, mates and interference" width="100%"></a><br><sub>An assembly: parts, mates and interference</sub></td>
</tr>
<tr>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#verify-cut"><img src="docs/assets/demos/verify-model/test_cut_reports_the_volume_it_removed.gif" alt="A cut reports the volume it removed" width="100%"></a><br><sub>A cut reports the volume it removed</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#verify-revolve"><img src="docs/assets/demos/verify-model/test_revolve_reports_the_volume_it_added.gif" alt="A revolve reports the volume it added" width="100%"></a><br><sub>A revolve reports the volume it added</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#verify-round"><img src="docs/assets/demos/verify-model/test_round_part_size_is_exact.gif" alt="A round part's size is exact" width="100%"></a><br><sub>A round part's size is exact</sub></td>
</tr>
<tr>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#verify-selection"><img src="docs/assets/demos/verify-model/test_reading_the_model_keeps_the_selection.gif" alt="Reading the model keeps the selection" width="100%"></a><br><sub>Reading the model keeps the selection</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#package-block"><img src="docs/assets/demos/drawing-package/test_generate_drawing_package_on_a_block.gif" alt="A full drawing package from one call" width="100%"></a><br><sub>A full drawing package from one call</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#sheet-scale"><img src="docs/assets/demos/drawing-package/test_set_sheet_scale_halves_the_views.gif" alt="Setting the sheet scale" width="100%"></a><br><sub>Setting the sheet scale</sub></td>
</tr>
<tr>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#bom"><img src="docs/assets/demos/drawing-package/test_insert_bom_table_lists_both_parts.gif" alt="A BOM on an assembly drawing" width="100%"></a><br><sub>A BOM on an assembly drawing</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#insert-model-dimensions"><img src="docs/assets/demos/drawing-dimensions/test_insert_model_dimensions_shows_each_dimension_once.gif" alt="Each model dimension shown once" width="100%"></a><br><sub>Each model dimension shown once</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#arrange-dimensions"><img src="docs/assets/demos/drawing-dimensions/test_arrange_dimensions_clears_every_overlap.gif" alt="Clearing every overlap" width="100%"></a><br><sub>Clearing every overlap</sub></td>
</tr>
<tr>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#material"><img src="docs/assets/demos/engineering-data/test_material_applies_and_changes_mass.gif" alt="Material and mass" width="100%"></a><br><sub>Material and mass</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#dimensions-and-measure"><img src="docs/assets/demos/engineering-data/test_dimensions_list_and_measure.gif" alt="Listing dimensions and measuring a face" width="100%"></a><br><sub>Listing dimensions and measuring a face</sub></td>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#flat-pattern"><img src="docs/assets/demos/engineering-data/test_export_flat_pattern_writes_a_dxf.gif" alt="Flat pattern of a sheet-metal part" width="100%"></a><br><sub>Flat pattern of a sheet-metal part</sub></td>
</tr>
<tr>
<td width="33%" valign="top"><a href="https://andrewbartels1.github.io/SolidworksMCP-python/demos/#custom-property"><img src="docs/assets/demos/engineering-data/test_custom_property_round_trip.gif" alt="Custom properties" width="100%"></a><br><sub>Custom properties</sub></td>
</tr>
</table>

**[See every demo in the docs](https://andrewbartels1.github.io/SolidworksMCP-python/demos/)**: what each one shows, its prompt, every tool call with its arguments (all 58 for the demo at the top), and how to run them yourself.

## Supported Today

- Windows + SolidWorks COM automation for the main CAD lifecycle.
- Tested on SolidWorks 2026. Earlier versions may work but are untested; if you try one, please [open an issue](https://github.com/andrewbartels1/SolidworksMCP-python/issues/new/choose) with what worked.
- Modeling, sketching, drawing, analysis, export, automation, templates, and macro tools.

## Not Yet / Simulated

- Mock adapter output is simulated and should not be treated as engineering truth.
- Live 3D viewport streaming in a UI.
- Checkpoint-level interference validation.
- Simple simulation and fluid workflows
- Simple Topology Optimization via SimulationXpress etc.

## Install

You need Windows 10 or 11 and SolidWorks (opened at least once). In PowerShell, install [uv](https://docs.astral.sh/uv/), then open a new PowerShell window and run setup:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uvx solidworks-mcp-python setup
```

uv fetches Python 3.13 and the server from PyPI by itself; nothing to clone. The guided setup then:

1. finds your SolidWorks version and the MCP clients on your PC: Claude Desktop, Claude Code, VS Code, Cursor and LM Studio;
2. lets you pick which clients to connect;
3. starts the server once to check that it lists its tools (in mock mode, so SolidWorks isn't touched);
4. adds a `solidworks` entry to each client you picked, then tells you what to restart.

Nothing needs a login or an API key, and the server runs only on your PC. Setup changes only the `solidworks` entry in each client's config. It backs the file up first and never shows or changes your other servers. Other entries that start this server the old way (`run-mcp.ps1` and the like) are offered for removal, so tools don't load twice.

**To check it worked:** open SolidWorks, restart your client, and ask *"What model is open in SolidWorks?"*

The package is `solidworks-mcp-python`. `uvx solidworks-mcp` installs a different project. To work on the server itself, [install from a clone](https://andrewbartels1.github.io/SolidworksMCP-python/getting-started/installation/#install-from-source). More fixes are in [Troubleshooting](https://andrewbartels1.github.io/SolidworksMCP-python/getting-started/installation/#troubleshooting).

## Connect your client

Run setup again whenever you want to add a client:

```powershell
uvx solidworks-mcp-python setup
```

| Option | What it does |
| --- | --- |
| `--client claude-desktop` | Configure one client without the list. Repeat it for several (`claude-code`, `vscode`, `cursor`, `lmstudio`). |
| `--dry-run` | Show what would change, and change nothing. |
| `--yes` | Don't ask: configure every client found. |
| `--remove` | Take the `solidworks` entry out again. |
| `--replace-old` | Remove older entries for this server without asking. |
| `--mock` | Configure mock mode, which answers without SolidWorks (for trying the tools). |
| `--year 2026` | The SolidWorks release to start the server with. Default: the newest installed. |

To set up a client by hand instead, each one runs `uvx solidworks-mcp-python --year 2026`, with your SolidWorks year. `--year` names your installed SolidWorks release and is required for real SolidWorks; setup fills it in for you. It picks which SolidWorks API the lookup tools answer for. Without it, the server logs a warning and uses the newest installed release. If a client can't find `uvx`, use its full path, from `(Get-Command uvx).Source`.

<details>
<summary><b>Claude Desktop</b></summary>

Add this to `claude_desktop_config.json`, alongside anything already in it. Depending on how Claude Desktop was installed, the file is in one of:

- `%LOCALAPPDATA%\Claude-Data\claude_<id>\` (current releases)
- `%LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\Roaming\Claude\`
- `%APPDATA%\Claude\`

```json
{
  "mcpServers": {
    "solidworks": {
      "command": "uvx",
      "args": ["solidworks-mcp-python", "--year", "2026"]
    }
  }
}
```

Quit Claude Desktop from the system tray (closing the window isn't enough) and reopen it. **Settings > Developer** should show `solidworks` as running.

</details>

<details>
<summary><b>Claude Code</b></summary>

```powershell
claude mcp add --scope user solidworks -- uvx solidworks-mcp-python --year 2026
```

Run `/mcp` in a new session to check that `solidworks` is connected.

</details>

<details>
<summary><b>VS Code</b></summary>

Add this to `%APPDATA%\Code\User\mcp.json`:

```json
{
  "servers": {
    "solidworks": {
      "type": "stdio",
      "command": "uvx",
      "args": ["solidworks-mcp-python", "--year", "2026"]
    }
  }
}
```

Run **MCP: List Servers** from the Command Palette and start `solidworks`. Its output should end with `Discovered 155 tools` (the count grows as tools are added).

</details>

<details>
<summary><b>LM Studio</b></summary>

Add this to `%USERPROFILE%\.lmstudio\mcp.json`:

```json
{
  "mcpServers": {
    "solidworks": {
      "command": "uvx",
      "args": ["solidworks-mcp-python", "--year", "2026"]
    }
  }
}
```

Restart LM Studio and enable `solidworks` in the Program tab.

</details>

For mock mode, which needs no SolidWorks, use `"args": ["solidworks-mcp-python", "--mock"]`. Linux and WSL work for the docs, the tests and mock mode, but not for driving SolidWorks.

<details>
<summary><b>Optional features (environment variables)</b></summary>

Set these in your client's `env` block for the server, or in the shell before starting it by hand. Every `SOLIDWORKS_MCP_<FIELD>` maps to the config field of the same name.

**SolidWorks-as-Code session logging (off by default).** Logs every adapter tool call to a local SQLite database, so a session can be replayed or exported as a runnable Python script (see [docs/getting-started/solidworks-as-code.md](docs/getting-started/solidworks-as-code.md)).

| Variable | Default | Meaning |
| --- | --- | --- |
| `SOLIDWORKS_MCP_SOC_LOGGING_ENABLED` | `false` | Turn logging on. |
| `SOLIDWORKS_MCP_SOC_SESSION_ID` | *(generated)* | Session name to log under. If unset while logging is on, a `soc-YYYYMMDD-HHMMSS` id is generated at startup. |
| `SOLIDWORKS_MCP_SOC_DB_PATH` | `.solidworks_mcp/agent_memory.sqlite3` | Override the database file. |

```powershell
$env:SOLIDWORKS_MCP_SOC_LOGGING_ENABLED = "true"
$env:SOLIDWORKS_MCP_SOC_SESSION_ID = "my-bracket"
.\.venv\Scripts\solidworks-mcp.exe
# ...work in your MCP client...
.\.venv\Scripts\python.exe -m solidworks_mcp.agents.soc_exporter my-bracket my_bracket.py
```

It works only with the circuit-breaker adapter wrapper (the default for real SolidWorks); the mock adapter does not log.

**API docs index auto-refresh (on by default).** The API-lookup tools (`lookup_api_interface`, `lookup_api_method`, `find_related_api_members`) and `search_solidworks_api_help` read a JSON index built by `discover_solidworks_docs`. When the index is older than the threshold, the next lookup rebuilds it.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SOLIDWORKS_MCP_DOCS_INDEX_AUTO_REFRESH` | `true` | Rebuild a stale index automatically. No-op without SolidWorks + win32com; a failed rebuild keeps serving the existing index. |
| `SOLIDWORKS_MCP_DOCS_INDEX_MAX_AGE_DAYS` | `21` | Age after which the index counts as stale. |

</details>

## Teach your agent the workflow

Each tool's description says what that tool does. The `solidworks-mcp` skill covers what spans tools: the order to build in (sketch, close it, then the feature), which inputs take millimetres and which take metres, how to pick faces and edges, checking the result with `verify_model`, recovering from errors, and the tools that don't work yet. Install it into Claude Code with:

```powershell
uvx solidworks-mcp-python skill install
```

That writes `~/.claude/skills/solidworks-mcp/`. Add `--project` for the current project's `.claude/skills`, or `--dir <folder>` for another agent's skills folder. It writes only that folder and needs no login. Re-run it after an upgrade.

Clients that read MCP resources don't need the install: the server serves the same skill at `skill://solidworks-mcp/SKILL.md`, and points to it in the instructions it sends when a client connects. More: [Agent skill](docs/agents/agent-skill.md).

## Contributing

`install.ps1` gives you an editable install, so code changes take effect the next time a client starts the server. For the development tools, install the extras:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,test,docs]"
```

`.\dev-commands.ps1` lists the common workflows:

- `dev-install`: install or update the local dev environment
- `dev-test`: run the standard test suite (the CI-safe subset)
- `dev-test-full`: run the full suite, including smoke and integration paths
- `dev-lint` and `dev-format`: lint checks and formatting
- `dev-docs-build`, `dev-docs-strict` and `dev-docs-audit`: build the docs, build them failing on warnings, or write an audit report to `.generated/docs`

To mirror GitHub Actions CI locally (Ubuntu, the conda env from `solidworks_mcp.yml`, and `make test`), run `.\scripts\run-ci-local.ps1`. The first run builds the image; add `-NoBuild` to re-run tests without rebuilding.

## Docs

- Main docs site: <https://andrewbartels1.github.io/SolidworksMCP-python/>
- Home/overview: [docs/index.md](docs/index.md)

Key docs sections:

- Getting Started: [docs/getting-started](docs/getting-started)
- MCP Server Guide: [docs/user-guide](docs/user-guide)
- Tool Catalog: [docs/user-guide/tool-catalog](docs/user-guide/tool-catalog)
- Agents and Skills: [docs/agents](docs/agents)
- Planning/Roadmap: [docs/planning](docs/planning)

Direct links:

- [Installation](docs/getting-started/installation.md)
- [Quick Start](docs/getting-started/quickstart.md)
- [Tutorial: U-Joint Assembly Build](docs/getting-started/tutorials/u-joint-assembly-build.md)
- [Tutorial Tracks](docs/getting-started/tutorial-tracks.md)
- [VS Code MCP Setup](docs/getting-started/vscode-mcp-setup.md)
- [Architecture](docs/user-guide/architecture.md)
- [Agents and Prompt Testing](docs/agents/agents-and-testing.md)
- [PydanticAI and Schemas](docs/agents/pydantic-ai-and-schemas.md)

## License

MIT License. See [LICENSE](LICENSE).
