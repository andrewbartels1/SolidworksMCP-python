## Why

Issue #95: an agent writing a SolidWorks call can look up a method's
parameters but not the values of the enums they take. Guessing goes wrong:
building `set_units`, `swUnitSystem_IPS` turned out to be 3, not 4, and the
user preference `swUnitSystem` 263, not 48. The values live in SolidWorks'
constants type library (`swconst.tlb`), installed and registered beside the
main one, which the lookups don't read today.

## What Changes

- The API index also reads the constants type library: every enum, its
  description, and each member's name and integer value (983 enums on
  SolidWorks 2026). The index format goes from 2.0 to 2.1, so a saved
  index is rebuilt once (about a second).
- A new tool, `get_api_enum`: an enum name gives its members and values.
  A member name (`swUnitSystem_IPS`) gives the enum it belongs to, with
  that member marked. Names match regardless of case. No match says so.
- The tool needs SolidWorks installed, not running (`needs:installed`),
  like the other lookups. 140 tools.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `tools/api-help-lookup`: adds the enum lookup the spec deferred to #95.

## Impact

`tools/type_library.py`, `tools/docs_discovery.py`, the hints, levels and
requirements tables, the docs-discovery catalog page and tool counts, the
live API-lookup test.
