## Why

Two gaps in the COM coverage, queue items 36 and 39:

- **Appearance.** An agent can't colour anything. A part, a feature, a body or
  one face can't be given a colour, so a demo, a rendering or a multi-body
  part can't show which piece is which, and a colour can't be read back.
  The boolean-logic demo had to colour its bodies with direct COM in the
  test (queue item 35).
- **Reference and analysis extras.** There is no coordinate system, no
  centre-of-mass point, no bounding box feature and no section properties
  of a face. These are what an agent needs to report stock size (bounding
  box), place a measurement or export frame (coordinate system), mark where
  the mass sits (centre of mass), or check a cross-section (area, centroid
  and second moments of area of a face, for a beam or a bracket).

## What Changes

- **`set_appearance`**: colour the part, a feature, a body or the face at a
  point, as `[r, g, b]` (0-255) or `#rrggbb`, with an optional
  transparency; or with `reset: true` remove a feature's, body's or face's
  colour so the one above it shows again. The reply reads the colour back.
- **`get_appearance`**: read the colour of the part, a feature, a body or a
  face, and say which level it comes from.
- **`create_coordinate_system`**: a coordinate system with its origin at a
  point given in mm, axes along the model's.
  The reply reads its transform back.
- **`create_center_of_mass_point`**: the Center of Mass reference point,
  with the centre of mass in mm.
- **`create_bounding_box`**: SolidWorks's Bounding Box feature around the
  part's bodies, with the box size in mm.
- **`get_section_properties`**: area, centroid, second moments of area about
  the centroid, the polar moment and the principal moments of a planar face,
  picked by a point on it.
- Six new tools, beta until their live demo.

## Capabilities

### New Capabilities

- `tools/appearance`: `set_appearance` and `get_appearance`.
- `tools/reference-extras`: `create_coordinate_system`,
  `create_center_of_mass_point`, `create_bounding_box` and
  `get_section_properties`.

### Modified Capabilities

None.

## Impact

- New adapter modules `adapters/solidworks/appearance.py` and
  `adapters/solidworks/reference_extras.py`, with mocks
  `adapters/mock_appearance.py` and `adapters/mock_reference_extras.py`.
  New non-abstract methods in `adapters/base.py`, with wrappers in
  `circuit_breaker.py` and `connection_pool.py`.
- New tool modules `tools/appearance.py` and `tools/reference_extras.py`,
  registered in `tools/__init__.py`; the families join the core toolset.
- Docs: two tool-catalog pages, counts, the skill's workflow notes, the
  CHANGELOG.
- Tests mirror `src`; a live test `tests/live/test_live_sw_appearance_and_reference.py`
  with one refusal per tool family.
