## Purpose

An agent writes text in a sketch, laid along a line it drew, at a chosen
letter height, so a cut or an extrusion can deboss or emboss it. The text
may show a custom property (`$PRP:"name"`); a property linked to a
dimension makes the text follow that dimension, and so an equation.

## ADDED Requirements

### Requirement: Text in the open sketch
`add_sketch_text` SHALL add `text` to the open sketch, its letters
`height` millimetres tall (default 3.5), spaced normally, and reply with
the text's `id`, the text SolidWorks shows (a `$PRP:` link resolved) and
the height. Without a line it SHALL start at `x`, `y` (mm, sketch
coordinates). It SHALL fail with `invalid_input` for empty text or a
height that isn't positive, and with an error when no sketch is open.

#### Scenario: A word on a bar's top face
- **WHEN** a sketch is open on a plane at a 120 x 20 x 4 mm bar's top
  face, and `add_sketch_text` is called with `text` `solidworksmcp` and
  `height` 4
- **THEN** the reply gives the text's `id`, `solidworksmcp` and height 4,
  and a 0.5 mm cut from that sketch removes material from the bar

### Requirement: Text along a line
Given `along`, the `id` of a line or centreline in the open sketch,
`add_sketch_text` SHALL lay the text along that line from its start, as
SolidWorks does when a curve is selected before inserting text. An `id`
that isn't in the open sketch SHALL fail and add nothing.

#### Scenario: Along a construction line
- **WHEN** a centreline is drawn from (10, 0) to (110, 0) and
  `add_sketch_text` is called with `along` its `id`
- **THEN** the text runs along the line from x = 10 mm

### Requirement: Mirrored text reads from the other side
With `mirror` true, `add_sketch_text` SHALL mirror the text left to right,
so text cut into a face the sketch plane looks at from behind (the
underside of a part) reads correctly from that side.

#### Scenario: Text under a handle
- **WHEN** text is added with `mirror` true on a plane at a handle's
  underside and cut in
- **THEN** seen from below, the text reads left to right

### Requirement: A linked property follows its dimension
Text containing `$PRP:"name"`, where the custom property `name` holds a
dimension's name in quotes (`"D1@Sketch3"`), SHALL show that dimension's
value, and show the new value after the dimension changes and the model
rebuilds (for example through an equation).

#### Scenario: The size changes
- **WHEN** the text is `size $PRP:"WrenchSize" mm`, `WrenchSize` is
  `"D1@Sketch3"` at 13 mm, and an equation changes `D1@Sketch3` to 19 mm
- **THEN** the text reads `size 19.00 mm`
