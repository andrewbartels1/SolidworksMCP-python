## 1. Probe

- [x] 1.1 Probe colour (part, feature, face), the coordinate system (vertex,
      edge, 3D-sketch point), the centre of mass, the bounding box and the
      section properties on SolidWorks 2026 (two scripts; answers in
      design.md)

## 2. Adapter

- [x] 2.1 `base.py`: parameter models and non-abstract methods for the six
      operations; wrappers in `circuit_breaker.py` and `connection_pool.py`
- [x] 2.2 `adapters/solidworks/appearance.py`: set, reset and read colours
- [x] 2.3 `adapters/solidworks/reference_extras.py`: coordinate system,
      centre-of-mass point, bounding box, section properties
- [x] 2.4 Mocks: `mock_appearance.py`, `mock_reference_extras.py`
- [x] 2.5 Pure helpers (colour parsing and conversion, the section array,
      the transform) in `adapters/appearance_rules.py`

## 3. Tools

- [x] 3.1 `tools/appearance.py`: `set_appearance`, `get_appearance`
- [x] 3.2 `tools/reference_extras.py`: `create_coordinate_system`,
      `create_center_of_mass_point`, `create_bounding_box`,
      `get_section_properties`
- [x] 3.3 Register both; toolset families; support levels (beta); hints;
      error classifier rules

## 4. Tests

- [x] 4.1 Unit tests mirroring src, 100% coverage
- [x] 4.2 Live test `tests/live/test_live_sw_appearance_and_reference.py`:
      a block with a coloured feature and face, read back; a coordinate
      system, the centre of mass, the bounding box, the section properties;
      one refusal per family. Run it, look at the images.
      (Both passed on SolidWorks 2026, 2026-11-28; the picture showed the
      blue top face, green sides, an orange face, the coordinate system at
      the corner and the box. The first run caught the flip flags doing
      nothing; they were dropped.)

## 5. Docs

- [x] 5.1 Tool-catalog pages, index and counts, tools overview, skill
      workflow notes, description standard verbs, CHANGELOG, llms.txt
- [ ] 5.2 A demo section and GIF once the user has seen it
