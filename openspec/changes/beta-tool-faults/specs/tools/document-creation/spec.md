## Purpose

What the document and sketch creation tools apply from their inputs, and the
names they report back.

## ADDED Requirements

### Requirement: A new part gets the material asked for

`create_part` with `material` SHALL assign that material to the new part. When
the material isn't found, the part SHALL still be created, and the reply SHALL
say the material wasn't applied and which library was searched.

#### Scenario: A known material
- **WHEN** an agent creates a part with `material: "AISI 304"`
- **THEN** reading the part's material afterwards returns AISI 304

#### Scenario: An unknown material
- **WHEN** an agent creates a part with `material: "Unobtainium"`
- **THEN** the part is created, and the reply carries a `warning` that the material wasn't found

### Requirement: A new sketch has the name asked for

`create_sketch` with `sketch_name` SHALL name the new sketch that in the
feature tree. The reply's sketch name SHALL always be the name the feature tree
shows.

#### Scenario: A named sketch
- **WHEN** an agent creates a sketch with `sketch_name: "HoleProfile"`
- **THEN** the feature tree shows `HoleProfile`, and `create_cut_extrude` with `sketch_name: "HoleProfile"` uses it

#### Scenario: A name already taken
- **WHEN** the requested name is already in the tree
- **THEN** the sketch keeps SolidWorks' own name, and the reply gives that name with a `warning` saying why
