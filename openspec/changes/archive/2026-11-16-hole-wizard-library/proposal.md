## Why

`create_hole` guesses at Hole Wizard sizes. An agent can't see which sizes a
standard has, so it passes a screw size where SolidWorks wants a drill
diameter, and the hole fails with nothing to go on: live on 2026-11-15, a
simple ISO `M4` made no hole, and the fix guessed `Ø4.0`, the wrong hole for
an M4 screw (its clearance hole is the `M4` row of ISO's Screw Clearances
table). SolidWorks keeps every standard, hole type and size in its Toolbox
library, a SQLite file the API never exposes; reading it lets the agent pick
a real size and lets `create_hole` say which sizes exist when one doesn't.

## What Changes

- New read-only tool `list_hole_sizes`: for a standard and hole type, the
  Hole Wizard's hole types (e.g. ISO simple: "Drill sizes", "Screw
  Clearances", "Tap Drills", "Dowel Holes") and each one's enabled sizes; with
  one type and size, that size's dimensions (diameter, counterbore diameter
  and depth, thread pitch).
- `create_hole` takes an optional `fastener` (a hole type's name from
  `list_hole_sizes`) in place of the fixed type per hole kind, and checks the
  size against the library before calling SolidWorks. An unknown size is
  refused with the nearest sizes that exist.
- A simple ISO hole sized `M4` uses the Screw Clearances table (a clearance
  hole for an M4 screw); a bare diameter (`4`, `Ø4`) uses Drill Sizes. This
  replaces the `M4` -> `Ø4.0` conversion added on 2026-11-15.
- More standards for both tools: ANSI metric, DIN and JIS beside ISO and
  ANSI inch, from `swWzdHoleStandards_e`.
- Out of scope, its own change later: adding sizes or a whole standard to the
  library from a config file (the user's request of 2026-11-15). See
  design.md, "Adding sizes".

## Capabilities

### New Capabilities

- `tools/hole-wizard-library`: reading the installed Hole Wizard library
  (standards, hole types, sizes, dimensions), and `create_hole`'s use of it
  to choose the hole type and refuse sizes the library doesn't have.

### Modified Capabilities

None. `tools/hole-wizard` is still in the unarchived `part-feature-depth`
change; its requirements are unchanged, and the size check is specified
in the new capability.

## Impact

- Adapter interface: a new `list_hole_sizes` method in `base.py`, wired
  through the circuit breaker, connection pool and both adapters. The real
  adapter reads a file, not COM: no COM threading or late-binding risk, and
  it works with SolidWorks closed. The mock adapter serves a small built-in
  library.
- `create_hole` in `tools/modeling.py` and `adapters/solidworks/part_features.py`.
- No new dependency (`sqlite3` is in the standard library). Read-only: the
  library file is opened `mode=ro&immutable=1` and never written.
- Docs: the modeling catalog, the skill's workflows, api-coverage.
- No GitHub issue; follows #105 (item 11).
