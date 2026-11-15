## MODIFIED Requirements

### Requirement: Response is always a flat list of feature descriptors
`list_features` SHALL always return a single flat list of feature
descriptors, regardless of document type. Each descriptor SHALL contain
`name`, `type`, `suppressed`, and `position`, exactly as it does today for
Part documents. The response SHALL NOT be restructured into a nested
object (for example, separate `components`/`assembly_features`
collections) for any document type, because existing callers (feature-tree
diffing, feature-family classification, and the MCP tool's `count` field)
depend on the result being a flat list. Within each document, the
descriptors SHALL be in feature-tree order (oldest first), each feature
SHALL appear once, and its `position` SHALL be its place in that order,
however SolidWorks was walked to find it.

#### Scenario: Listing features on a Part
- **WHEN** `list_features` is called with the active document being a
  `.SLDPRT` Part
- **THEN** the result is a flat list of that Part's own feature
  descriptors, in the same shape as before this change

#### Scenario: The forward walk stops early
- **WHEN** SolidWorks stops the feature walk at the system folders, so the
  remaining features are found newest first
- **THEN** the result is still in tree order: the default planes come
  before `Plane1`, and `Plane1` before the cut sketched on it
