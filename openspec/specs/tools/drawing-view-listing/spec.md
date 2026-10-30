# tools/drawing-view-listing Specification

## Purpose
Lets an MCP caller see which views already exist on the active drawing, as
the read-side complement to `create_drawing_view` / `add_drawing_view`, so an
agent can target an existing view by name (for example for `auto_center_marks`).
## Requirements
### Requirement: list_drawing_views is exposed as an MCP tool
The server SHALL register a `list_drawing_views` tool that takes no
document-specific input, reads the active document, and returns
`status: "success"`, a human-readable `message`, a `views` list of view-name
strings (sheet-format pseudo-views excluded), a `count`, and `execution_time`.

#### Scenario: Drawing with standard views
- **WHEN** `list_drawing_views` is called while a drawing with three model
  views is active
- **THEN** the response has `status: "success"`, `views` contains the three
  view names, and `count` is 3

#### Scenario: Drawing with no views
- **WHEN** `list_drawing_views` is called on a drawing with an empty sheet
- **THEN** the response has `status: "success"`, `views` is empty and
  `count` is 0

### Requirement: list_drawing_views errors on a non-drawing document
`list_drawing_views` SHALL return `status: "error"` with a message naming the
requirement for a drawing document when the active document is a part or an
assembly, or when no document is active. It SHALL NOT raise.

#### Scenario: Part document is active
- **WHEN** `list_drawing_views` is called while a part is active
- **THEN** the response has `status: "error"` and the message says a drawing
  document is required

