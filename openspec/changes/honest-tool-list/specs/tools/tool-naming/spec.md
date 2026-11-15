## Purpose

Tool names use one verb per meaning, so an agent can guess a tool's name
and tell two tools apart from their names alone.

## ADDED Requirements

### Requirement: One verb per meaning
A tool's name SHALL start with a verb from the list in
`docs/agents/tool-description-standard.md`:

| Verb | Meaning |
| --- | --- |
| `create_` | makes a new document, or a new feature built from a sketch or acting on the whole body (extrusion, rib, hole, shell) |
| `add_` | adds an entity to an open sketch or a drawing, or treats edges or faces of an existing body (fillet, chamfer, draft, thread) |
| `pattern_`, `mirror_` | repeats existing features |
| `sketch_` | an operation on the open sketch's entities (offset, mirror, pattern, convert) |
| `get_` | reads one thing |
| `list_` | reads a collection |
| `set_` | changes one value |
| `open_`, `save_`, `close_`, `export_` | file operations |
| `check_`, `verify_`, `measure_`, `compare_` | read-only checks |

Names already registered that break the list SHALL be listed as
exceptions in the same file, and the check SHALL fail on any other name
that breaks it.

#### Scenario: A new tool with an unlisted verb
- **WHEN** a tool named `make_hole` is registered
- **THEN** the naming check fails and names the tool and the verb list

#### Scenario: An existing exception
- **WHEN** `insert_component` is registered
- **THEN** the check passes because it is a listed exception
