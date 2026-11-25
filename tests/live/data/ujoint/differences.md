# U-joint replay: how today's server answers the session's calls

`with_skill_calls.json` holds the 294 tool calls a Claude Code session made
for the U-joint prompt, each with how it ended then. `replay_2026-11-25.json`
holds the same calls with how they end on today's server (replayed through an
in-memory MCP client on SolidWorks 2026, 2026-11-25). The replay is not part
of any test run; `tests/live/demo_ujoint_replay.py` uses the record when it
is run by name to record the demo.

The session's own three failures (calls 1, 28 and 88) still fail. Nine calls
end differently, and all nine come from three names the agent made up. The
server the session ran on accepted those names without a word; today's server
refuses them and says why.

| Call | Tool | Input | Then | Now | Why |
|-----:|------|-------|------|-----|-----|
| 83 | `create_revolve` | `sketch_name: "stub"`, `axis_entity: "centerline"` | success | error | There is no sketch `stub`, and `centerline` is a word, not an axis. The old server ignored both and revolved the last sketch about its centreline, which happened to be what the agent meant. |
| 85 | `create_sketch` | `plane: "Plane1"` | success | error | `Plane1` had been renamed to `PivotPlane` (call 65); the plane call 84 made is `Plane3`. The old server fell back to the Top plane, so the session drew this sketch on the wrong plane. |
| 86 | `add_rectangle` | | success | error | No sketch is open (call 85). |
| 87 | `exit_sketch` | | success | error | No sketch is open (call 85). |
| 89 | `delete_feature` | `name: "Sketch7"` | success | error | `Sketch7` was the sketch from calls 85 to 87, which wasn't made. |
| 93 | `create_cut_extrude` | `sketch_name: "Sketch8"` | success | error | One sketch fewer, so call 90's sketch is `Sketch7`, not `Sketch8`. |
| 94 | `delete_feature` | `name: "Cut-Extrude9"` | success | error | Call 93's cut wasn't made. |
| 96 | `create_cut_extrude` | `sketch_name: "Sketch8"` | success | error | As call 93. |
| 210 | `create_revolve` | `axis_entity: "centerline"` | success | error | As call 83. `axis_entity` takes the id `add_centerline` returned (`Centerline_1`) since 2026-11-25, but not the word. |

## What it shows

- The recorded session "succeeded" at calls 83, 85 and 210 only because the
  old server ignored a name it couldn't find. At call 85 that put a sketch on
  the wrong plane without telling the agent.
- Calls 86 to 96 are one cascade: once call 85 is refused, every later name
  that counted on its sketch is off by one.
- A replay can't recover from a refusal the way the agent would: the agent
  reads the error and tries again; the replay sends the next recorded call.

## Open questions

- Should `create_revolve` take `axis_entity: "centerline"` when the sketch
  has exactly one centreline? It would make calls 83 and 210 succeed for the
  right reason, but it is a guess the server makes for the agent.
- Rerunning the prompt on today's server would give a new session to record,
  with the agent recovering from these refusals itself.
