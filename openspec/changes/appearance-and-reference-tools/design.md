## Context

Motivation: see proposal.md, under "Why".

**Probes (SolidWorks 2026 SP4, 2026-11-28; scratch part, closed unsaved):**

- **Colour.** A colour is nine doubles: R, G, B (0-1), ambient, diffuse,
  specular, shininess, transparency, emission. It must be passed as a
  `VARIANT(VT_ARRAY | VT_R8)` (`com_utils.double_array`): a plain list was
  misread (the boolean demo's bodies came out green and see-through).
  - Part: `IModelDoc2.MaterialPropertyValues` (read/write property). Reads
    `[0.894, 0.894, 0.894, 1, 1, 0.5, 0.3125, 0, 0]` on a new part.
  - Feature: `IFeature.SetMaterialPropertyValues2(values, 1, None)` (1 =
    this configuration); `GetMaterialPropertyValues2(1, None)` reads it, all
    `-1` when the feature has none; `RemoveMaterialProperty2(1, None)`
    removes it.
  - Face: `IFace2.MaterialPropertyValues` (property), `None` when the face
    has none; `RemoveMaterialProperty2(1, None)` removes it.
  - Body: `IBody2.MaterialPropertyValues2` (property; set live in the
    boolean demo).
  - A face's colour shows over its feature's, a feature's over the part's
    (image: blue top face, green sides, red part colour hidden).
- **Coordinate system.** `IFeatureManager.InsertCoordinateSystem(xFlip,
  yFlip, zFlip)` with the origin selected with mark 1 and no axes selected
  gives model-aligned axes. A vertex works, and so does a point in a 3D
  sketch (`Insert3DSketch`, `CreatePoint(m)`, `Insert3DSketch` again; the
  point selects as `Point1@3DSketch1`, type `EXTSKETCHPOINT`). An x axis
  taken from an edge follows the edge's own direction (it came out
  reversed), so edges are not offered. The transform reads back through
  `IModelDocExtension.GetCoordinateSystemTransformByName(name).ArrayData`:
  rotation rows `[0:9]`, origin in metres `[9:12]`.
- **Centre of mass.** `IFeatureManager.InsertCenterOfMass()` returns the
  feature, named "Center of Mass". The centre comes from
  `IModelDocExtension.CreateMassProperty().CenterOfMass` (metres), with the
  extension flagged `IModelDocExtension` (unflagged, it was read as a
  property and failed).
- **Bounding box.** `IFeatureManager.InsertGlobalBoundingBox(0, hidden,
  surfaces, status)` needs `status` as `VARIANT(VT_BYREF | VT_I4, 0)`;
  a plain `0` is a type mismatch. It makes "Bounding Box" (type
  `BoundingBoxProfileFeat`). Type 0 is best fit.
- **Section properties.** `IModelDocExtension.GetSectionProperties2(None)`
  reads the current selection; passing the face in an array returned
  status 1 and zeros. The array: `[0]` status (0 = ok), `[1]` area m²,
  `[2:5]` centroid m, `[5:11]` Ixx, Iyy, Izz, Ixy, Izx, Iyz at the centroid
  (m⁴), `[11]` polar moment, `[12]` the principal axes' angle, `[13:15]`
  the principal moments. A 40 mm square: area 0.0016, centroid
  `(0, 0.01, 0)`, Ixx = Izz = 2.133e-7, polar 4.267e-7.

## Goals / Non-Goals

**Goals:** colour any level and read it back; the four reference extras,
each read back from SolidWorks rather than echoed.

**Non-Goals:**
- Appearances from the library (`.p2m` files, textures), decals, scenes.
- Colours in assemblies (component overrides).
- Coordinate systems from edges, faces or angles, or with reversed axes:
  only a point with model-aligned axes. The flip flags of
  `InsertCoordinateSystem` do nothing when no axis is selected (the live
  test asked for z flipped and read +z back), so reversed axes need axis
  lines drawn and selected, a later change.
- Bounding boxes on a custom plane (type 1) or in sheet-metal cut lists.
- Section properties of sketches or of a plane through a body.

## Decisions

1. **One `set_appearance`, a target by field.** Exactly one of `feature`,
   `body`, `face_point`, or none for the part. Two targets are refused.
   `reset` removes an override; resetting the part is refused.
2. **Colours as the user says them.** `[r, g, b]` 0-255 or `#rrggbb` in;
   both out, plus transparency. The other six values keep SolidWorks's
   defaults for shading (ambient 1, diffuse 1, specular 0.5, shininess
   0.3125, emission 0); only transparency is the caller's.
3. **Faces by point.** A face is picked by `SelectByID2("", "FACE", x, y, z)`
   after a rebuild (pitfall #13), the way `select_face_edges` does.
4. **Read back, not echo.** Each reply reads SolidWorks: the colour after
   setting it, the coordinate system's transform, the centre of mass, the
   box's size (the part box after the feature), the section array.
5. **Module layout.** Appearance and the reference extras are separate
   modules, adapter and mock, so neither grows `features.py` or
   `modeling.py` (queue item 40).
6. **Errors.** Unknown targets and two targets are `invalid_input`
   (`InputRefused`); a SolidWorks call that makes nothing raises a
   message the classifier maps to `feature_not_built`.
