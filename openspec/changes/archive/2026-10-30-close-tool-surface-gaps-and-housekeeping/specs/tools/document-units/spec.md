## Purpose

Lets a caller set a document's unit system, closing the gap where
`create_part`'s `units` parameter is accepted but currently ignored.

## ADDED Requirements

### Requirement: Active document's unit system can be set
The adapter SHALL expose `set_units`, accepting one of `mm`, `cm`, `m`,
`in`, `ft`, applying it to the active document and returning the applied
value. It SHALL fail clearly (not raise) when there's no active document.

#### Scenario: Setting units on the active document
- **WHEN** `set_units` is called with a supported unit system and there's
  an active document
- **THEN** the document's unit system changes and the response reports it

#### Scenario: No active document
- **WHEN** `set_units` is called with no document open
- **THEN** the response status indicates failure

### Requirement: create_part's units parameter takes effect
`create_part`'s `units` parameter SHALL apply the requested unit system
to the new part before returning, via the same mechanism as `set_units`,
instead of being ignored.

#### Scenario: New part is created with requested units
- **WHEN** `create_part` is called with a `units` value other than the
  template default
- **THEN** the new part's unit system matches the requested value
