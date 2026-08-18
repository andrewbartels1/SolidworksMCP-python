## Purpose

Given a CAD-generation skill family the calling model has already selected (`solidworks-native`, `text-to-cad`, `mesh-concept`), returns a validated, bounded execution contract for that branch — allowed tools, required validation steps, and expected outputs — so the assistant never has to invent a capability the SolidWorks adapter doesn't actually have. Exposed as a plain MCP tool with no internal LLM call: classification of *which* family fits a request is the calling model's own judgment, made from this tool's parameter description, not a nested API call this capability makes on its behalf.

## ADDED Requirements

### Requirement: Return a bounded execution contract for a caller-selected skill family
The system SHALL accept a skill family argument of exactly one of `solidworks-native`, `text-to-cad`, or `mesh-concept`, and SHALL return a route that includes the selected family, an allowed-tools list, required validation steps, expected outputs, and a fallback value.

#### Scenario: solidworks-native requested
- **WHEN** the caller selects `family: "solidworks-native"`
- **THEN** the system returns a route with `family: "solidworks-native"`, `fallback: null`, and an `allowed_tools` list drawn from the full SolidWorks-native tool surface

#### Scenario: text-to-cad requested
- **WHEN** the caller selects `family: "text-to-cad"`
- **THEN** the system returns a route with `family: "text-to-cad"`

#### Scenario: mesh-concept requested
- **WHEN** the caller selects `family: "mesh-concept"`
- **THEN** the system returns a route with `family: "mesh-concept"`

### Requirement: Allowed tools are validated against the real adapter interface
The system SHALL validate every tool name in a route's `allowed_tools` against the `SolidWorksAdapter` interface (`src/solidworks_mcp/adapters/base.py`) at call time, not against a hardcoded list, and SHALL fail closed when a proposed tool does not correspond to a real adapter capability.

#### Scenario: Proposed tool exists on the adapter interface
- **WHEN** the router selects a branch and every tool it names corresponds to a public capability on `SolidWorksAdapter`
- **THEN** the route is returned with those tools in `allowed_tools`

#### Scenario: Proposed tool does not exist on the adapter interface
- **WHEN** the router would otherwise include a tool name that does not correspond to a public capability on `SolidWorksAdapter`
- **THEN** the system SHALL exclude that tool from `allowed_tools` and SHALL NOT return a route that references a nonexistent capability

### Requirement: solidworks-native branch reuses existing COM/VBA routing unchanged
The system SHALL NOT introduce any separate COM/VBA decision logic for the `solidworks-native` branch — execution of tools named in that branch's `allowed_tools` continues to go through the existing `IntelligentRouter`/`ComplexityAnalyzer` path unchanged.

#### Scenario: solidworks-native route names only real, already-routed tools
- **WHEN** a route with `family: "solidworks-native"` is returned
- **THEN** every tool named in its `allowed_tools` is one that already dispatches through the existing `IntelligentRouter`/`ComplexityAnalyzer` path with no separate COM/VBA decision logic introduced by this capability

### Requirement: Branches without a backing implementation are stubbed, not broken
The system SHALL return an explicit, clearly-flagged stub response for any skill family that has no backing implementation yet, rather than returning a route that silently fails or executes an unimplemented path.

#### Scenario: text-to-cad requested before its implementation lands
- **WHEN** `family: "text-to-cad"` is requested and the text-to-cad execution branch is not yet implemented
- **THEN** the system returns a route whose `fallback` field explicitly states the branch is unavailable, with an empty `allowed_tools`, and does not attempt to execute it

#### Scenario: mesh-concept requested with no backing implementation
- **WHEN** `family: "mesh-concept"` is requested and no mesh-concept execution path exists
- **THEN** the system returns a route whose `fallback` field explicitly states the branch is unavailable, with an empty `allowed_tools`, and does not attempt to execute it

### Requirement: No internal LLM or network call
The system SHALL NOT make any outbound LLM/API call as part of returning a route. Classification of which family fits a given request is the responsibility of whichever model is already driving the calling MCP session, not this capability.

#### Scenario: Route returned without any model call
- **WHEN** `get_skill_route` is called with a valid family argument
- **THEN** the system returns a route using only local computation (adapter-class introspection and static per-branch data) and makes no request to any LLM provider or external service
