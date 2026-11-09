## Purpose

Give users a form to send their selftest results, and show everyone which
SolidWorks releases the server has passed the selftest on.

## ADDED Requirements

### Requirement: A compatibility issue form

The repository SHALL offer a "Compatibility report" issue form that asks
for the selftest summary (required), the SolidWorks version and service
pack (required), the Windows version, and the MCP client and model. Its
summary field SHALL accept being filled from the link the selftest prints.
The form SHALL label new issues `compatibility`.

#### Scenario: The selftest link fills the form

- **WHEN** the user opens the link the selftest printed
- **THEN** the compatibility form opens with the summary field already holding the selftest's summary

### Requirement: The form is easy to find

The README's "Tested on" line and the feedback form SHALL point to the
compatibility form and say how to run the selftest.

#### Scenario: A user on SolidWorks 2022 reads the README

- **WHEN** a user reads that the server is tested on SolidWorks 2026
- **THEN** the same line tells them to run `solidworks-mcp-python selftest` and send the result with the compatibility form

### Requirement: The releases verified so far are listed

The docs SHALL have a page listing each SolidWorks release and service
pack the selftest has run on, with the date, each area's result and a link
to the report. It SHALL start with SolidWorks 2026 SP4.0 from the live
test. A release with a failing area SHALL still be listed, with the area
that failed.

#### Scenario: A report with a failure is added

- **WHEN** a report from SolidWorks 2024 SP5 shows the drawing area failing
- **THEN** the page lists 2024 SP5 with part, assembly and export PASS, drawing FAIL, and a link to that issue
