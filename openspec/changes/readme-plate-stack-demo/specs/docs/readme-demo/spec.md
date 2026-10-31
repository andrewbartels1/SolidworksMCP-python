## ADDED Requirements

### Requirement: README opens with a checked live demo

The README SHALL show, near the top, an animated capture of a live
SolidWorks session that goes from a written prompt to a finished drawing.
Every step shown SHALL be a call to a registered MCP tool, and every number
the demo claims SHALL be checked against a hand calculation by the test that
made the capture.

#### Scenario: A visitor reads the README

- **WHEN** a visitor opens the README
- **THEN** the demo GIF appears before the installation instructions
- **AND** the prompt it answers is shown as text beside it
- **AND** the tool calls are listed beneath it, folded by default

#### Scenario: The demo states what it is

- **WHEN** the README describes the demo
- **THEN** it says the calls are replayed by a test, not a recorded model
  session

### Requirement: The demo can be rerun

The demo SHALL be produced by one live test that can be rerun with
`tests/scripts/live_demo.ps1`. Run with a capture folder, it SHALL write the
frames, the GIF and a JSON transcript of every tool call (tool name,
arguments and status).

#### Scenario: Rerunning the demo

- **WHEN** the maintainer runs `live_demo.ps1` on the demo test with
  `-CaptureDir docs/assets/demos/readme`
- **THEN** the test passes only if every tool call succeeded and every
  checked number matched
- **AND** the folder holds the GIF and `plate_stack_calls.json`

#### Scenario: A step fails

- **WHEN** any tool call returns an error
- **THEN** the test fails and names the tool and its reply
