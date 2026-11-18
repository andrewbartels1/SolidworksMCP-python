## Purpose

An agent reads, adds, changes and deletes the equations and global
variables of the active part or assembly, so one value can drive several
dimensions and the model stays consistent when it changes.

## ADDED Requirements

### Requirement: List equations
`list_equations` SHALL return every equation of the active part or
assembly in SolidWorks' order, each with `index`, `name` (the left-hand
side without quotes), `expression` (the right-hand side), `kind`
(`global_variable`, `dimension` or `other`) and `value` (the solved value
SolidWorks reports, or null when it has none). A model with no equations
SHALL give an empty list, not an error.

#### Scenario: A part with a global variable driving a dimension
- **WHEN** the part has `"Width" = 60mm` and `"D1@Sketch1" = "Width" / 2`
- **THEN** the reply lists `Width` as a `global_variable` with value 60
  and `D1@Sketch1` as a `dimension` with value 30

#### Scenario: No equations
- **WHEN** the part has none
- **THEN** the reply has an empty `equations` list and status `success`

### Requirement: Add or change an equation
`set_equation` SHALL take `name` and `expression`, and `configurations`
(`all` by default, `this`, or a list of names). A `name` with an `@` is a
dimension and SHALL be one the model has; any other name is a global
variable. When an equation for `name` exists (names compared without
regard to case) its expression SHALL be replaced; otherwise one SHALL be
added. The model SHALL be solved and rebuilt, and the reply SHALL give
the equation as SolidWorks stored it, its value, and whether it was
`added` or `changed`.

#### Scenario: A global variable drives a dimension
- **WHEN** `set_equation` is called with `Width` = `60mm`, then with
  `D1@Sketch1` = `"Width" / 2`
- **THEN** the sketch dimension reads 30 mm, and setting `Width` to `80mm`
  makes it read 40 mm

#### Scenario: An expression SolidWorks refuses
- **WHEN** `expression` is `"NoSuchVariable" * 2`
- **THEN** the call fails with `equation_refused`, and `list_equations`
  is unchanged

#### Scenario: A dimension the model doesn't have
- **WHEN** `name` is `D9@NoSuchSketch`
- **THEN** the call fails with `invalid_input` pointing to
  `list_model_dimensions`, and nothing is added

#### Scenario: One configuration only
- **WHEN** `configurations` is `["Long"]` and the part has `Default` and
  `Long`
- **THEN** the value applies in `Long`, and `Default` keeps its own

### Requirement: Delete an equation
`delete_equation` SHALL take `name`, remove that equation, and reply with
the names left. A dimension it drove SHALL keep its last value.

#### Scenario: Deleting a driving equation
- **WHEN** `D1@Sketch1` = `"Width" / 2` is deleted
- **THEN** `list_equations` no longer lists it and the dimension still
  reads its last value

#### Scenario: An unknown name
- **WHEN** no equation is named `name`
- **THEN** the call fails with `invalid_input` listing the equation names
