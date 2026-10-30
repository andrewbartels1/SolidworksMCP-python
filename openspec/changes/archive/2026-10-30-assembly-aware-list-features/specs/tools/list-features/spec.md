## Purpose

Defines what the `list_features` adapter operation returns for Part,
Assembly, and nested-Assembly SolidWorks documents, so an LLM agent can
reliably read a document's full feature tree regardless of document type,
without changing the flat-list response shape existing callers depend on.

## ADDED Requirements

### Requirement: Response is always a flat list of feature descriptors
`list_features` SHALL always return a single flat list of feature
descriptors, regardless of document type. Each descriptor SHALL contain
`name`, `type`, `suppressed`, and `position`, exactly as it does today for
Part documents. The response SHALL NOT be restructured into a nested
object (for example, separate `components`/`assembly_features`
collections) for any document type, because existing callers (feature-tree
diffing, feature-family classification, and the MCP tool's `count` field)
depend on the result being a flat list.

#### Scenario: Listing features on a Part
- **WHEN** `list_features` is called with the active document being a
  `.SLDPRT` Part
- **THEN** the result is a flat list of that Part's own feature
  descriptors, in the same shape as before this change

### Requirement: Feature descriptors identify their originating component
Each feature descriptor SHALL carry a `component` field and a
`component_path` field. For a feature that belongs to the document's own
feature manager — every feature on a Part, and an Assembly's own
top-level features (planes, origin, assembly sketches, mates) — both
fields SHALL be `None`. For a feature belonging to a resolved component's
underlying document, `component` SHALL be the component's name and
`component_path` SHALL be that document's file path.

#### Scenario: Assembly-level feature is unattributed
- **WHEN** `list_features` is called on an Assembly and a feature belongs
  to the assembly document itself (not to any component)
- **THEN** that feature's descriptor has `component: None` and
  `component_path: None`

#### Scenario: Component feature is attributed to its component
- **WHEN** `list_features` is called on an Assembly containing a
  component instance, and that component's underlying document has its
  own features
- **THEN** each of those features appears in the flat result list with
  `component` set to the component's name and `component_path` set to
  the component's document path

### Requirement: Suppression filtering applies independently per document
The `include_suppressed` parameter SHALL be honored independently for the
assembly's own features and for each component's features: a suppressed
feature belonging to one component's document SHALL NOT affect whether a
feature belonging to another component, or to the assembly itself, is
included.

#### Scenario: Suppressed feature in one component does not affect another
- **WHEN** `list_features(include_suppressed=False)` is called on an
  Assembly where Component A has one suppressed feature and Component B
  has none
- **THEN** Component A's suppressed feature is excluded from the result
  while Component B's features are unaffected, and the assembly's own
  features are filtered by the same rule independently

### Requirement: Sub-assemblies are traversed up to a bounded depth
When a component instance is itself an Assembly (a sub-assembly), its
components SHALL be traversed the same way as top-level components — their
features flattened into the same result list, tagged with their own
component name — up to a configurable recursion depth via a new optional
`max_assembly_depth` parameter. The default depth SHALL be 2 (top-level
assembly, plus one level of sub-assembly). A component instance beyond the
configured depth SHALL still appear in the result as a single descriptor
identifying it by name and path, rather than being silently omitted.

#### Scenario: Sub-assembly one level deep is traversed
- **WHEN** `list_features` is called on a top-level Assembly containing a
  sub-assembly component, and the sub-assembly's own components are Parts
- **THEN** the result includes feature descriptors for the Parts inside
  the sub-assembly, tagged with their own component name, not just the
  sub-assembly's own assembly-level features

#### Scenario: Recursion depth limit is respected
- **WHEN** `list_features` is called with a component chain deeper than
  the configured `max_assembly_depth`
- **THEN** a component beyond the configured depth appears in the result
  as one descriptor identified by name and path, rather than causing an
  error, infinite recursion, or being silently dropped

### Requirement: Unresolvable components do not fail the whole call
When a component instance cannot be resolved to an underlying document
(for example, it is suppressed, lightweight-and-not-loaded, or its
referenced file is missing), `list_features` SHALL still include one
descriptor for that component identifying it by name, rather than raising
an error that discards results already gathered for other components.

#### Scenario: One missing component does not block the others
- **WHEN** `list_features` is called on an Assembly where one component's
  referenced part file cannot be resolved and the other components
  resolve normally
- **THEN** the result still includes feature descriptors for the
  components that resolved successfully, plus one descriptor identifying
  the unresolved component by name

### Requirement: Feature descriptors identify their component's parent component
Each feature descriptor SHALL carry a `component_parent` field: the
immediate parent component's name when `component` is itself nested inside
another component (a sub-assembly), or `None` when `component` is a
top-level component, or when `component` is itself `None` (the document's
own feature). This SHALL be sufficient to reconstruct the real
parent/child structure between components, distinguishing "nested inside"
from "also present somewhere in this assembly."

#### Scenario: Nested component identifies its parent
- **WHEN** `list_features` is called on an Assembly containing a
  sub-assembly component, and that sub-assembly's own component has
  features in the result
- **THEN** each of those features' `component_parent` equals the
  sub-assembly component's name

#### Scenario: Top-level component has no parent
- **WHEN** `list_features` is called on an Assembly and a feature belongs
  to a top-level component (not nested inside another component)
- **THEN** that feature's `component_parent` is `None`

### Requirement: A nested component tree can be derived from the flat result
A pure function SHALL be available that reconstructs a nested
component/sub-component tree — each node holding its own features and a
mapping of its child components — from the flat list `list_features`
returns, using `component`/`component_path`/`component_parent`. This
SHALL NOT change `list_features`' own return shape; it is a derived view
for callers that want to inspect assembly structure directly.

#### Scenario: Building the tree from a nested assembly result
- **WHEN** the tree-building function is given the flat result of
  `list_features` on an Assembly containing a sub-assembly component with
  its own child components
- **THEN** the sub-assembly's child components appear nested under the
  sub-assembly's node in the tree, not as siblings of the sub-assembly at
  the top level

#### Scenario: Building the tree from a Part result
- **WHEN** the tree-building function is given the flat result of
  `list_features` on a Part (no descriptor has a non-`None` `component`)
- **THEN** the tree's top-level `components` mapping is empty and all
  descriptors appear in the tree's own `features` list
