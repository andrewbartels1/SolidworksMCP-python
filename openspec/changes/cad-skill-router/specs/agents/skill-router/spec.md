## Purpose

Classifies a user's CAD-generation intent into one of three named skill-family branches (`solidworks-native`, `text-to-cad`, `mesh-concept`) and returns a validated, bounded execution contract for that branch, so the assistant never has to guess which generation workflow to use or invent capabilities outside what the SolidWorks adapter actually supports.

## ADDED Requirements

### Requirement: Classify CAD-generation intent into a named skill family
The system SHALL classify an incoming CAD-generation request into exactly one of `solidworks-native`, `text-to-cad`, or `mesh-concept`, returning a route that includes the selected family, an allowed-tools list, required validation steps, expected outputs, and a confidence score.

#### Scenario: Request classified as solidworks-native
- **WHEN** a user asks to edit an existing SolidWorks feature tree, create an assembly, or perform another editable-modeling operation
- **THEN** the system returns a route with `family: "solidworks-native"` and an `allowed_tools` list drawn from the existing SolidWorks-native tool surface

#### Scenario: Request classified as text-to-cad
- **WHEN** a user asks to generate a new part from a natural-language description with no existing SolidWorks document open
- **THEN** the system returns a route with `family: "text-to-cad"`

#### Scenario: Request classified as mesh-concept
- **WHEN** a user asks for quick concept geometry or a browser-preview-only result with no need for an editable SolidWorks feature tree
- **THEN** the system returns a route with `family: "mesh-concept"`

### Requirement: Allowed tools are validated against the real adapter interface
The system SHALL validate every tool name in a route's `allowed_tools` against the `SolidWorksAdapter` interface (`src/solidworks_mcp/adapters/base.py`) at classification time, not against a hardcoded list, and SHALL fail closed when a proposed tool does not correspond to a real adapter capability.

#### Scenario: Proposed tool exists on the adapter interface
- **WHEN** the router selects a branch and every tool it names corresponds to a public capability on `SolidWorksAdapter`
- **THEN** the route is returned with those tools in `allowed_tools`

#### Scenario: Proposed tool does not exist on the adapter interface
- **WHEN** the router would otherwise include a tool name that does not correspond to a public capability on `SolidWorksAdapter`
- **THEN** the system SHALL exclude that tool from `allowed_tools` and SHALL NOT return a route that references a nonexistent capability

### Requirement: solidworks-native branch reuses existing COM/VBA routing unchanged
The system SHALL dispatch the `solidworks-native` branch through the existing `llm_service.py` clarify/inspect/go pipeline and the existing `IntelligentRouter`/`ComplexityAnalyzer` COM/VBA routing, and SHALL NOT duplicate or replace that routing logic.

#### Scenario: solidworks-native route executes through existing pipeline
- **WHEN** a route with `family: "solidworks-native"` is dispatched
- **THEN** execution proceeds through the existing `IntelligentRouter`/`ComplexityAnalyzer` path with no separate COM/VBA decision logic introduced by this capability

### Requirement: Branches without a backing implementation are stubbed, not broken
The system SHALL return an explicit, clearly-flagged stub response for any skill family that has no backing implementation yet, rather than returning a route that silently fails or executes an unimplemented path.

#### Scenario: text-to-cad requested before its implementation lands
- **WHEN** a request classifies as `family: "text-to-cad"` and the text-to-cad execution branch is not yet implemented or is feature-flagged off
- **THEN** the system returns a route whose `fallback` field explicitly states the branch is unavailable, and does not attempt to execute it

#### Scenario: mesh-concept requested with no backing implementation
- **WHEN** a request classifies as `family: "mesh-concept"` and no mesh-concept execution path exists
- **THEN** the system returns a route whose `fallback` field explicitly states the branch is unavailable, and does not attempt to execute it

### Requirement: Low-confidence requests fall back instead of guessing
The system SHALL include a numeric `confidence` value on every route and SHALL populate `fallback` with a concrete next step when confidence is below the system's threshold, instead of committing to a single branch it is not confident about.

#### Scenario: Ambiguous request
- **WHEN** a request does not clearly indicate which of the three skill families applies
- **THEN** the system returns a route with a low `confidence` value and a non-empty `fallback` describing what to do instead of silently picking one branch
