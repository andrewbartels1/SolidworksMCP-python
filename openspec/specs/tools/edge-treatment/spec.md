# tools/edge-treatment Specification

## Purpose
What `add_chamfer` and `add_fillet` treat for each `edge_names` entry: a face point treats every edge of that face, an edge point treats one edge, and an entry that selects nothing fails without changing the part.
## Requirements
### Requirement: A face point treats every edge of that face

When an `add_chamfer` or `add_fillet` `edge_names` entry is a face point
(`"face:x,y,z"`, in metres), the tool SHALL chamfer or fillet every edge
bounding the face that the point lies on, in one feature. It SHALL NOT act
on a different face, even a larger or nearer-looking one.

#### Scenario: The face a hole opens onto

- **WHEN** `add_chamfer` is called with a 0.5 mm distance and a point on
  the 30×30 mm face of the test coupon that its Ø5.5 mm hole opens onto
- **THEN** the hole rim and the face's four 30 mm edges are chamfered, and
  the material removed is 17.1241 mm³ within 0.001 mm³ (the five edges,
  less each of the four mitred corners counted once)

#### Scenario: A side face

- **WHEN** the point lies on one of the coupon's 30×15 mm side faces
- **THEN** only that face's four edges are chamfered: 11.0833 mm³ within
  0.001 mm³

### Requirement: An edge point treats the edge it lies on

When an entry is an edge point (`"x,y,z"`, in metres), the tool SHALL
treat the one edge that the point lies on.

#### Scenario: A face and an edge in one call

- **WHEN** `add_chamfer` is called with a point on the coupon's hole face
  and a point on a 30 mm edge of the opposite face
- **THEN** both are chamfered in one feature, and the material removed is
  the hole face's 17.1241 mm³ plus the edge's 3.75 mm³, within 0.001 mm³

#### Scenario: A fillet on one edge

- **WHEN** `add_fillet` is called with a 1 mm radius and a point on a
  30 mm edge that no other treated edge meets
- **THEN** that edge is filleted: (1 − π/4)·30 = 6.4381 mm³ within
  0.001 mm³

### Requirement: A point on nothing fails clearly

When a face or edge point lies more than 0.5 mm from every face or edge
of the model, or a name matches no edge, the tool SHALL return
`status: "error"` with a message that says which entry failed, and SHALL
leave the part unchanged: no feature and no change in volume. A call with
several entries SHALL fail as a whole when any entry fails. The failure
SHALL be logged as one warning line, not as a fault with a traceback.

#### Scenario: A point inside the block

- **WHEN** `add_fillet` is called with a face point 5 mm inside the coupon
- **THEN** the response is an error naming the point and a nearest
  distance of 5 mm, and the part is unchanged

#### Scenario: An edge name that doesn't exist

- **WHEN** `add_chamfer` is called with a name that matches no edge
- **THEN** the response is an error naming it, and the part is unchanged

#### Scenario: One good entry and one bad one

- **WHEN** `add_chamfer` is called with a point on the hole face and a
  name that matches no edge
- **THEN** the response is an error and the part is unchanged

