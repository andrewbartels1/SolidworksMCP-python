# tools/feature-selection Specification

## Purpose
Lets an MCP caller select a named feature, sketch, reference plane or assembly
component, or every edge of a face, in the active document. Typical uses are
highlighting before `export_image` and setting up selection-driven operations
such as `add_chamfer`/`add_fillet` with empty `edge_names`. Selection is
single by default and multi on request, and the result is honest: anything
that could not be selected is an error, never a quiet success.
## Requirements
### Requirement: select_feature is exposed as an MCP tool
The server SHALL register a `select_feature` tool with a required, non-blank
`feature_name` string and an optional `append` boolean (default `false`).
With `append: false` the named entity SHALL replace the current selection.
With `append: true` it SHALL be added to the current selection.

On success the response SHALL contain `status: "success"`, `message`,
`execution_time` and a `data` payload with:
- `selected: true`
- the requested `feature_name`
- `selected_name`: the name actually matched (may carry a `@document`
  qualifier)
- `entity_type`: what resolved it
- `selection_count`: the number of entities selected afterwards

#### Scenario: Select a solid feature in a part
- **WHEN** `select_feature` is called with `"Boss-Extrude1"` on a part that
  has that feature
- **THEN** the response has `status: "success"`, `data.selected` is true,
  and the feature is the only current selection in SolidWorks

#### Scenario: Select a sketch
- **WHEN** `select_feature` is called with `"Sketch1"` on a part that has
  that sketch
- **THEN** the response has `status: "success"` and the sketch is selected

#### Scenario: Qualified name
- **WHEN** `select_feature` is called with `"Boss-Extrude1@Part1"`
- **THEN** it resolves the same feature as the bare name

#### Scenario: Append to the selection
- **WHEN** `select_feature("Sketch1")` is followed by
  `select_feature("Boss-Extrude1", append=true)`
- **THEN** both are selected and `data.selection_count` is 2

### Requirement: select_feature never reports a false success
`select_feature` SHALL return `status: "error"` in each of these cases:
- the name matches nothing selectable in the active document
- no document is active
- the name is blank

It SHALL NOT raise, and SHALL NOT return `status: "success"` with
`selected: false`. The error message SHALL include the requested name.

#### Scenario: Unknown feature name
- **WHEN** `select_feature` is called with `"NoSuchFeature"`
- **THEN** the response has `status: "error"` and the message contains
  `NoSuchFeature`

#### Scenario: Blank name
- **WHEN** `select_feature` is called with `""` or whitespace
- **THEN** input validation rejects it with `status: "error"` before any
  SolidWorks call

### Requirement: Every edge of a face can be multi-selected
The server SHALL register a `select_face_edges` tool that selects every edge
bounding one face of the active part as a single multi-selection. The face is
identified by exactly one of these inputs:
- `point`: `[x, y, z]` in millimetres, a point on the face
- `side`: one of `+X -X +Y -Y +Z -Z`, or the aliases `right` (+X),
  `left` (-X), `top` (+Y), `bottom` (-Y), `front` (+Z), `back` (-Z),
  following SolidWorks' default view orientation. It resolves to the planar
  face whose outward normal matches that direction and lies furthest along
  it.
- `plane`: a reference plane name. It resolves to the body face lying on
  that plane.

Optional inputs:
- `edge_type`: `all` (default), `linear` or `circular`, to filter the edges
- `append`: boolean, default `false`. Adds the edges to the current
  selection instead of replacing it.

On success the response SHALL contain:
- `data.face`: the resolved face's center, normal and area
- `data.edges`: one entry per selected edge with its type
  (`linear`/`circular`/`other`), endpoints in mm, and length or radius
- `data.selection_count`

#### Scenario: Circular edges of the top face
- **WHEN** a box with a vertical through-hole is active and
  `select_face_edges(side="top", edge_type="circular")` is called
- **THEN** only the hole's rim edge on the top face is selected, and
  `data.edges` reports it as `circular` with the hole's radius

#### Scenario: All edges by point
- **WHEN** `select_face_edges(point=[x, y, z])` is called with a point on a
  rectangular face that has no holes
- **THEN** its four edges are selected and `data.selection_count` is 4

#### Scenario: Chain into a chamfer
- **WHEN** `select_face_edges(side="top", edge_type="circular")` is followed
  by `add_chamfer(distance=1, edge_names=[])`
- **THEN** the chamfer is applied to exactly the selected rim edge(s)

#### Scenario: By reference plane
- **WHEN** `select_face_edges(plane="Front Plane")` is called on a part with
  a face lying on the Front Plane
- **THEN** that face's edges are selected

### Requirement: select_face_edges fails clearly
`select_face_edges` SHALL return `status: "error"` (not raise) in each of
these cases:
- not exactly one of `point`/`side`/`plane` is given
- `side` or `edge_type` is not a recognised value
- no face matches
- the matched face has no edges of the requested `edge_type`
- the active document is not a part

The message SHALL say which of these happened.

#### Scenario: No matching face
- **WHEN** `select_face_edges(point=[1000, 1000, 1000])` is called
- **THEN** the response has `status: "error"` and the message says no face
  was found at that point

#### Scenario: No edges of the requested type
- **WHEN** `select_face_edges(side="top", edge_type="circular")` is called
  on a plain box
- **THEN** the response has `status: "error"` and the message says the face
  has no circular edges

### Requirement: Adapter interface declares the selection operations
Every adapter layer (base interface, circuit breaker, connection pool, mock,
real) SHALL expose:
- `select_feature(feature_name: str, append: bool = False)`
- `select_face_edges(point=None, side=None, plane=None, edge_type="all",
  append=False)`

They SHALL return the payloads above, and ERROR results for the failure
cases. The base interface defaults SHALL be ERROR results stating that the
adapter does not implement the operation. The mock adapter SHALL only report
`select_feature` success for feature names it is tracking for the active
model.

#### Scenario: Mock adapter unknown name
- **WHEN** the mock adapter's `select_feature` is called with a name it has
  never created
- **THEN** it returns an ERROR result naming the feature

