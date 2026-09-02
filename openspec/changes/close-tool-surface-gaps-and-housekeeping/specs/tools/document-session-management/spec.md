## Purpose

Lets a caller see which documents are open and switch the active one,
surfacing what the adapter already tracks internally.

## ADDED Requirements

### Requirement: Open documents can be enumerated
The adapter SHALL expose `list_open_documents`, returning each open
document's title, path, type, and whether it's the active document.

#### Scenario: Multiple documents open
- **WHEN** `list_open_documents` is called with two or more documents open
- **THEN** each appears with title, path, type, and `is_active`, and
  exactly one has `is_active: true`

#### Scenario: No documents open
- **WHEN** `list_open_documents` is called with nothing open
- **THEN** the result is an empty list, not an error

### Requirement: Active document can be switched
The adapter SHALL expose `activate_document`, which makes an open document
(identified by title or path) the active one, and SHALL fail clearly
(not raise) if that document isn't open.

#### Scenario: Activating an open document
- **WHEN** `activate_document` is called with an open, non-active
  document's title or path
- **THEN** that document becomes active

#### Scenario: Target document is not open
- **WHEN** `activate_document` is called with a title or path that
  matches no open document
- **THEN** the response status indicates failure and the active document
  is unchanged
