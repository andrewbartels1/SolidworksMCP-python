# adapters/release-compat Specification

## Purpose
TBD - created by archiving change solidworks-2024-reports-batch-2. Update Purpose after archive.
## Requirements
### Requirement: A call that works is made as before
A COM call routed through the compatibility layer SHALL be made exactly as it
is without the layer first, so a release where it works (SolidWorks 2026)
behaves the same.

#### Scenario: SolidWorks 2026
- **WHEN** `list_equations` runs on SolidWorks 2026
- **THEN** each `IEquationMgr` member is called as before and none is
  retried

### Requirement: "Member not found" is retried as the other dispatch kind
A call that fails with `DISP_E_MEMBERNOTFOUND` SHALL be retried once through
`IDispatch.Invoke` with `DISPATCH_METHOD | DISPATCH_PROPERTYGET` and the same
arguments; any other error SHALL be raised as it was.

#### Scenario: An indexed property answered only as a property
- **WHEN** `IEquationMgr.Equation(0)` says "Member not found" as a method call
- **THEN** it is read as a property with index 0 and the equation's text comes
  back

### Requirement: A report names what differs
Every member that needed the retry SHALL be recorded, and the selftest
summary SHALL list them, only when there are any.

#### Scenario: A selftest on SolidWorks 2024
- **WHEN** the selftest runs on a release where `IEquationMgr.GetCount` needs
  the retry
- **THEN** the summary has a row naming `IEquationMgr.GetCount`

### Requirement: Where something lands is measured and corrected
A tool whose result's position can differ between releases SHALL read the
position back and correct it, so the result is the same on each release.

#### Scenario: A note on SolidWorks 2024
- **WHEN** `add_note` asks for x = 30 mm and SolidWorks centres the note there
- **THEN** the note is moved so its top-left corner is at x = 30 mm, and its
  extent is in the reply

