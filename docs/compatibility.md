# Compatibility

The SolidWorks releases the selftest has been run on, and how each area
did. The server is developed against SolidWorks 2026; every other row comes
from a user's report.

## Check your release

With SolidWorks open and idle, run:

```powershell
uvx solidworks-mcp-python selftest
```

In about three minutes it checks four areas through the same MCP tools a
client calls, each against a hand calculation:

| Area | What it does | What it checks |
| --- | --- | --- |
| Part | A 40 × 20 × 10 mm block, then a Ø10 hole through it, then a 2 mm fillet on one edge; a Ø9.5 × 20 mm pin | Volume after each feature (8,000, then 7,214.60, then 7,180.27 mm³; the pin 1,417.64 mm³) and each bounding box |
| Assembly | The block and the pin, mated by two faces: concentric in the hole, bottoms flush | 2 components, 2 mates, no interference |
| Drawing | A new drawing with one isometric view of the block | Exactly one view |
| Export | The block as STEP | The file exists and isn't empty |

It saves only into a temporary folder it deletes afterwards. It closes only
the documents it opened, without saving them, and never touches one that
was open before it started.

It prints PASS, FAIL or SKIP per area, then a summary and a link that opens
the [compatibility report form](https://github.com/andrewbartels1/SolidworksMCP-python/issues/new?template=compatibility.yml)
with the summary filled in. A failing report is as useful as a passing one:
it shows what to fix. `--report selftest.md` also writes the summary to a
file. The exit code is 0 when every area passes, 1 when any fails or is
skipped, and 2 when it can't run (SolidWorks not installed or not running).

## Releases checked

| SolidWorks | Date | Part | Assembly | Drawing | Export | Report |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 SP4.0 (34.4.0), English | 2026-11-08 | PASS 8/8 | PASS 3/3 | PASS 1/1 | PASS 1/1 | the maintainer's run, and the live test `tests/live/test_live_sw_selftest.py` |
