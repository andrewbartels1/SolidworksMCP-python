## Purpose

The drawing `generate_drawing_package` builds has a title block whose
fields each fit their box, whatever the values' lengths.

## ADDED Requirements

### Requirement: Every linked field fits its box
The title-block step SHALL fit every sheet-format note linked to a property
(`$PRP:"name"` or `$PRPSHEET:"name"`): its text SHALL be shrunk until it
ends before the next note in its row (or the title block's right edge),
no smaller than the minimum height, and no larger than
`title_block_text_height_mm` when that is given. A property shown by more
than one note SHALL be fitted once, by its first note.

#### Scenario: A long material name
- **WHEN** the part's material name is longer than its cell
- **THEN** the reply's `title_block` has an entry for it with `fits` true,
  and its text height is below the format's

#### Scenario: A short value
- **WHEN** a field's value already fits
- **THEN** its entry has `fits` true and the same height before and after

### Requirement: Each fitted field is named in the reply
The reply's `title_block` SHALL name the DWG NO. `drawing number` and the
TITLE `title`; the drawing's own fields SHALL use the names
`update_title_block` takes, with spaces (`drawn by`, `drawn date`,
`revision`, `company`); any other field SHALL be named by its property.

#### Scenario: The ISO A3 format
- **WHEN** a drawing is generated on `a3 - iso`
- **THEN** `title_block` lists `drawing number` and `title`, and an entry
  for each other property the format links

### Requirement: The subtitle is the TITLE's second line
A `subtitle` SHALL be shown as a second line of the TITLE field (ISO 7200's
supplementary title), with the TITLE's text height at most 60% of the
format's (or the caller's cap, if smaller). The company field SHALL show
`company` only.

#### Scenario: A subtitle and no company
- **WHEN** `subtitle` is `Base support` and `company` is empty
- **THEN** the TITLE reads `Package Block` then `Base support`, and the
  company field is empty
