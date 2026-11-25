## ADDED Requirements

### Requirement: Default planes and the origin are found by identity
A tool that is given a default plane SHALL find it in the document's own
feature tree by type and order (the first three reference planes are Front,
Top and Right; the origin is the origin feature), not by its English name.
`Front`, `Top`, `Right`, `XY` (Top), `XZ` (Front), `YZ` (Right) and the
full English names (`Front Plane`...) all name a default plane, in any
case. Any other name is used as given. A `@component@assembly` suffix
finds the plane in that component's tree.

#### Scenario: A sketch on a translated part
- **WHEN** a part's default planes are named `Plan de face`,
  `Plan de dessus` and `Plan de droite` and `create_sketch` is called with
  `plane` `Top`
- **THEN** the sketch opens on `Plan de dessus`

#### Scenario: A renamed default plane
- **WHEN** the user renamed the Top plane `Base` and a tool is given
  `Top Plane`
- **THEN** the tool uses `Base`

#### Scenario: A plane the user made
- **WHEN** a tool is given `Plane1`
- **THEN** `Plane1` is used as given, and a missing one fails as `not_found`

#### Scenario: The answer is per document
- **WHEN** two documents are open with differently named default planes
- **THEN** each tool call resolves the names in the document it works on

### Requirement: Standard views by ID
Showing a standard view (front, back, left, right, top, bottom,
isometric, trimetric, dimetric, normal to) SHALL use the view's
`swStandardViews_e` ID where SolidWorks takes one. A drawing view of a
standard model view SHALL take the view's name from that model's own view
list, in its position for that view, so it is right in any language.

#### Scenario: An isometric drawing view on a French install
- **WHEN** `create_drawing_view` asks for `isometric` and the model's view
  list names it `*Isométrique`
- **THEN** the view is placed from `*Isométrique`

### Requirement: No process-wide change to COM
Resolving default names SHALL NOT change how COM calls behave outside the
call that needs a default entity: no hook on pywin32's dispatch, no cache
shared across documents.

#### Scenario: Other calls are untouched
- **WHEN** any tool calls a SolidWorks method that takes no default name
- **THEN** the call runs exactly as pywin32 makes it

### Requirement: The language is reported
`get_model_info` and the selftest report SHALL give the install's language
(`GetCurrentLanguage`). A default plane that can't be found SHALL fail
naming the planes the document has and the language.

#### Scenario: A part with no default planes
- **WHEN** a document's tree has fewer than three reference planes before
  its origin and a tool is given `Top`
- **THEN** the call fails as `not_found`, listing the document's planes and
  the install's language
