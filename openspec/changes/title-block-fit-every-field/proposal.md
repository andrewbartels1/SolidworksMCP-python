## Why

`generate_drawing_package` shrinks the title block's DWG NO. and TITLE text
until each fits its box, but no other field. A long material name, company
or DRAWN BY value runs over the next cell the same way (#158, "Only two
fields are fitted"). The two fitted fields are named in code; every other
field is left as the format draws it.

## What Changes

- The title-block step fits **every field the sheet format links to a
  property** (`$PRP:"..."` or `$PRPSHEET:"..."`), the same way the two
  fitted today are: shrunk until its text ends before the next note in its
  row, never below the minimum height, and capped by
  `title_block_text_height_mm` when given.
- The reply's `title_block` lists each fitted field. The two fitted today
  keep their names (`drawing number`, `title`); the drawing's own fields
  use the names `update_title_block` takes (`drawn by`, `drawn date`,
  `revision`, `company`); any other is named by its property, as the format
  links it (e.g. `SW-Material`).
- A property the format shows twice is fitted once.

Out of scope: measuring against the format's cell lines instead of the
next note (#158's first point), and where `subtitle` goes (#158's third
point, a decision for the user).

## Capabilities

### New Capabilities

- `tools/drawing-package-title-block`: how the generated drawing's title
  block fields are fitted to their boxes.

### Modified Capabilities

None.

## Impact

- `adapters/solidworks/drawing_standard.py` (`_fit_title_block`, a helper
  reading the linked property); its unit tests.
- `generate_drawing_package`'s catalog entry, the CHANGELOG, the queue.
- Live: the existing `test_generate_drawing_package_on_a_block` evidence
  shows every field fitted.
- #158 (part of it).
