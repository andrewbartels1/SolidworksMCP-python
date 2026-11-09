## Purpose

`solidworks-mcp-python selftest` checks a user's SolidWorks setup through
the same MCP tools an agent calls, and prints a report they can send us.

## ADDED Requirements

### Requirement: One command checks the setup

`solidworks-mcp-python selftest` SHALL run the selftest, and
`solidworks-mcp-python --selftest` SHALL do the same. `--year` SHALL be
accepted as it is when starting the server. The selftest SHALL drive
SolidWorks through the registered MCP tools, called with plain dict
arguments, so it exercises the same path an MCP client does.

#### Scenario: The flag spelling works

- **WHEN** the user runs `solidworks-mcp-python --selftest --year 2026`
- **THEN** the selftest runs, exactly as `solidworks-mcp-python selftest --year 2026` would

### Requirement: The environment is reported

The report SHALL give the SolidWorks revision and language, the default
part, assembly and drawing templates with whether each file exists, the
`--year` in use, the operating system, and the Python, pywin32 and
package versions. A value that cannot be read SHALL be reported as
unknown, never guessed, and SHALL NOT stop the selftest.

#### Scenario: A missing template is reported, not fatal

- **WHEN** the default drawing template points at a file that does not exist
- **THEN** the environment section shows that path marked missing, and the other areas still run

### Requirement: Each area is checked against a hand calculation

The selftest SHALL check four areas in order: part, assembly, drawing and
export. Each check SHALL compare a value read back from SolidWorks with an
expected value worked out by hand, within a stated tolerance:

- part: volume and bounding box after the extrude, after the hole and
  after the fillet;
- assembly: component count, mate count, and no interference;
- drawing: the drawing has exactly one view of the part;
- export: the STEP file exists and is not empty.

An area whose setup step fails SHALL be FAIL with the tool's error message.
An area that needs a file an earlier area did not save (the assembly,
drawing and export use the saved parts) SHALL be SKIP, naming what it
needed. An area whose files were saved SHALL still run when an earlier
area failed a check, so one wrong value does not hide the other results.

#### Scenario: A wrong volume fails its area

- **WHEN** the part's volume after the hole differs from the hand calculation by more than the tolerance
- **THEN** the part area is FAIL, and its line shows the expected value, the measured value and the tolerance

#### Scenario: A failed part skips the rest

- **WHEN** the part area fails before the part is saved
- **THEN** the assembly, drawing and export areas are SKIP, each saying it needs the part

### Requirement: The report can be pasted into an issue

The selftest SHALL print one line per area (PASS, FAIL or SKIP, with the
checks passed out of the checks run), then a Markdown summary holding the
environment, each area's checks and the tools called. When the summary
fits, it SHALL also print a link that opens the compatibility issue form
with the summary filled in. With `--report <path>` it SHALL also write the
summary to that file. The report SHALL NOT include file paths under the
user's profile beyond the templates' file names, nor any MCP client
configuration.

#### Scenario: A long summary still gets to the form

- **WHEN** the summary is too long for a link
- **THEN** the selftest prints the plain issue-form link and tells the user to paste the summary printed above it

### Requirement: Exit codes say what happened

The selftest SHALL exit 0 when every area passes, 1 when any area fails or
is skipped, and 2 when it cannot run at all: not on Windows, SolidWorks not
installed, or SolidWorks not running. Exit 2 SHALL print what to do next.

#### Scenario: SolidWorks is not running

- **WHEN** the user runs the selftest and SolidWorks is not running
- **THEN** it does not start SolidWorks, prints "Start SolidWorks, wait for it to finish loading, then run this again", and exits 2

### Requirement: The user's documents are left alone

The selftest SHALL NOT save, close, activate-and-change or rebuild any
document that was open before it started. It SHALL save only into a new
temporary folder it creates, SHALL close only documents it opened, without
saving, and SHALL delete that folder at the end, also when an area fails
or the run is interrupted.

#### Scenario: A user's part stays open and unchanged

- **WHEN** the user has an unsaved part open and runs the selftest
- **THEN** after the selftest that part is still open, still unsaved, and still has the same features, and every document the selftest made is closed
