## ADDED Requirements

### Requirement: Colour the part, a feature, a body or a face
`set_appearance` SHALL take a `color`, either `[r, g, b]` with each value 0
to 255 or a `#rrggbb` string, and an optional `transparency` from 0 (opaque,
the default) to 1. It SHALL colour exactly one target: the whole part when
no target is given, or the feature named by `feature`, the body named by
`body` (as `list_bodies` names it), or the face at `face_point` (`[x, y, z]`
mm, a point on the face). The reply SHALL read the colour back from
SolidWorks and give it as `color` `[r, g, b]` (0-255), `hex` and
`transparency`, with `target` saying what was coloured.

A face's colour shows over its feature's, and a feature's over the part's
(checked live, SolidWorks 2026).

#### Scenario: A blue top face on a green block
- **WHEN** a 40 × 40 × 10 mm block's feature `Boss-Extrude1` is set to
  `#1fcc33` and the face at `[0, 10, 0]` to `[25, 76, 242]`
- **THEN** both calls succeed, each reply reads back the colour asked for
  (to the nearest 1/255), and the top face shows blue over the green sides

#### Scenario: Two targets at once
- **WHEN** `set_appearance` is given both `feature` and `face_point`
- **THEN** it fails with `invalid_input`, saying to give one target

#### Scenario: A target that doesn't exist
- **WHEN** `feature` names no feature, `body` no body, or `face_point`
  lies on no face
- **THEN** it fails with `invalid_input`; for a body the message lists the
  bodies there are

### Requirement: Remove a colour
`set_appearance` with `reset: true` and a `feature`, `body` or `face_point`
SHALL remove that target's own colour so the colour above it shows again,
and SHALL reply `color` null for it. `reset` on the whole part SHALL fail
with `invalid_input`: the part's colour is the base, not an override.

#### Scenario: A face back to its feature's colour
- **WHEN** a coloured face is reset
- **THEN** the call succeeds and `get_appearance` on that face reports the
  feature's colour, from `level` "feature"

### Requirement: Read a colour back
`get_appearance` SHALL take the same targets (none for the part) and reply
`color`, `hex`, `transparency` and `level`: the level the visible colour
comes from (`face`, `body`, `feature` or `part`), walking up from the
target until one has a colour of its own.

#### Scenario: An uncoloured face of a coloured feature
- **WHEN** only `Boss-Extrude1` is coloured and a side face is read
- **THEN** `get_appearance` gives the feature's colour with `level`
  "feature"
