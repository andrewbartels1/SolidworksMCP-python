## Purpose

Lets an agent see the Hole Wizard standards, hole types and sizes installed
with SolidWorks, and makes `create_hole` use real sizes only.

## ADDED Requirements

### Requirement: List the hole types and sizes of a standard

The `list_hole_sizes` tool SHALL return, for a `standard` (`iso`,
`ansi_inch`, `ansi_metric`, `din`, `jis`) and a `hole_type` (`simple`,
`counterbore`, `countersink`, `tapped`), every enabled Hole Wizard hole type
of that kind with its `name` and its enabled `sizes` in the library's order.
Disabled hole types and sizes SHALL be left out. It SHALL be read-only and
SHALL work whether or not SolidWorks is running.

#### Scenario: ISO simple holes

- **WHEN** `list_hole_sizes` is called with `standard: "iso"` and
  `hole_type: "simple"`
- **THEN** the reply lists "Drill sizes" (sizes such as `Ø6.0`) and "Screw
  Clearances" (sizes such as `M6`) among the hole types, each with its sizes

#### Scenario: Counterbores list screw types

- **WHEN** `hole_type` is `counterbore`
- **THEN** the hole types are screw types (for ISO, "Cap (4762)" among them)
  with the screw sizes each takes

### Requirement: One size's dimensions

Given a `fastener` (a hole type's name) and a `size`, `list_hole_sizes` SHALL
return that size's dimensions in millimetres (or inches for `ansi_inch`), as
the library stores them: the diameter, and where the type has them the
counterbore diameter and depth, the countersink diameter, and the thread
pitch.

#### Scenario: An ISO M6 cap screw counterbore

- **WHEN** called with `standard: "iso"`, `hole_type: "counterbore"`,
  `fastener: "Cap (4762)"`, `size: "M6"`
- **THEN** the reply gives the counterbore diameter and depth for M6

#### Scenario: A size the type doesn't have

- **WHEN** the size is not in that hole type's table
- **THEN** the call fails with the nearest sizes that exist

### Requirement: Filtering a long list

`list_hole_sizes` SHALL accept a `fastener` alone, returning only that hole
type and all its sizes, so a reply for one type stays short.

#### Scenario: Only screw clearances

- **WHEN** called with `fastener: "Screw Clearances"` and no `size`
- **THEN** only that hole type and its sizes are returned

### Requirement: An unreadable library is reported, not guessed

When the library can't be found or read, `list_hole_sizes` SHALL fail with
the path(s) it looked in and how to point it at the library; it SHALL NOT
return an empty list as if the standard had no sizes.

#### Scenario: No Toolbox installed

- **WHEN** no library file exists at any known location
- **THEN** the call fails naming the locations it tried and the
  `SOLIDWORKS_MCP_HOLE_LIBRARY` setting

### Requirement: create_hole uses real sizes

`create_hole` SHALL accept an optional `fastener` naming a hole type from
`list_hole_sizes`. Before asking SolidWorks for the hole, it SHALL check the
size is an enabled size of that hole type; an unknown size SHALL be refused
with the nearest sizes and no feature made. When the library can't be read,
the hole SHALL still be attempted, with a warning that the size wasn't
checked.

#### Scenario: A screw size on a simple ISO hole

- **WHEN** `create_hole` is called with `hole_type: "simple"`,
  `standard: "iso"`, `size: "M6"` and no `fastener`
- **THEN** the hole is an ISO screw clearance hole for M6, and the reply names
  the hole type used

#### Scenario: A drill diameter on a simple ISO hole

- **WHEN** the size is a bare diameter (`6`, `Ø6`, `6.0`)
- **THEN** the hole is the "Drill sizes" `Ø6.0` hole

#### Scenario: A size that doesn't exist

- **WHEN** `create_hole` is called with a size the hole type lacks
- **THEN** it fails before any feature is made, listing the nearest sizes
