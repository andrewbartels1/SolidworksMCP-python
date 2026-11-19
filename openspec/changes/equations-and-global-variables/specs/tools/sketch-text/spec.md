## Purpose

An agent writes text in a sketch, at a point or centred on one, at a
chosen letter height, so a cut or an extrusion can deboss or emboss it.
The text may show a custom property (`$PRP:"name"`); a property linked to
a dimension makes the text follow that dimension, and so an equation.

## ADDED Requirements

### Requirement: Text in the open sketch
`add_sketch_text` SHALL add `text` to the open sketch starting at `x`,
`y` (mm, sketch coordinates), its letters `height` millimetres tall
(default 3.5) and spaced normally, and reply with the text's `id`, the
text SolidWorks shows (a `$PRP:` link resolved) and the height. It SHALL
fail with `invalid_input` for empty text, a height that isn't positive or
a `center_at` that isn't three numbers, and with an error when no sketch
is open.

#### Scenario: A word on a bar's top face
- **WHEN** a sketch is open on a 120 x 30 x 4 mm bar's top face and
  `add_sketch_text` is called with `text` `solidworksmcp` and `height` 4
- **THEN** the reply gives the text's `id`, `solidworksmcp` and height 4,
  and a 0.3 mm cut from that sketch removes material from the bar

### Requirement: Text centred on a model point
Given `center_at`, a model point `[x, y, z]` in mm, `add_sketch_text`
SHALL move the text so the middle of its extent lies on that point
projected onto the sketch.

#### Scenario: The middle of a bar
- **WHEN** the bar runs from x = 0 to 120 and `center_at` is `[60, 2, 0]`
  on its top face
- **THEN** the text's middle is at x = 60 mm, across the bar's middle

#### Scenario: Read from the underside
- **WHEN** the sketch is opened on the bar's bottom face (`face_point`)
  and the text centred at `[60, -2, 0]`
- **THEN** seen from below the text reads left to right, centred

### Requirement: A linked property shows its dimension when written
Text containing `$PRP:"name"`, where the custom property `name` holds a
dimension's name in quotes (`"D1@Sketch3"`), SHALL show that dimension's
value at the moment the text is written. SolidWorks doesn't redraw sketch
text when the model rebuilds, so the text keeps that value until it is
written again (`set_sketch_text`).

#### Scenario: Written at 13 mm
- **WHEN** the text is `size $PRP:"WrenchSize" mm` and `WrenchSize` is
  `"D1@Sketch3"`, which is 13 mm
- **THEN** the text reads `size 13.00 mm`, and still does after an
  equation changes `D1@Sketch3` to 19 mm and the model rebuilds

### Requirement: Re-letter a sketch's text
`set_sketch_text` SHALL replace the text of every sketch text in the
named sketch with `text`, with the sketch open for editing (the only way
SolidWorks redraws it), close the sketch, rebuild, and reply with the
sketch, the text each showed before and what it shows now (links
resolved). A sketch that doesn't exist, or has no text, SHALL fail and
change nothing.

#### Scenario: The size changed
- **WHEN** the lettering above is in `Sketch12`, `D1@Sketch3` is now 19 mm,
  and `set_sketch_text` is called with `Sketch12` and the same
  `size $PRP:"WrenchSize" mm`
- **THEN** the reply gives `before` `size 13.00 mm` and `after`
  `size 19.00 mm`, and the cut from that sketch reads 19.00

#### Scenario: No such sketch
- **WHEN** `set_sketch_text` is called with `Sketch99`
- **THEN** it fails as not found and nothing changes
