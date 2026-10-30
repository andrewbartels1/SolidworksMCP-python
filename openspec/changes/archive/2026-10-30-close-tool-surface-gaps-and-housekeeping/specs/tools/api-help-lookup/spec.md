## Purpose

Gives a caller narrower, structured SolidWorks API lookups — method
signature, interface members, enum values, related members — alongside
the existing full-text `search_solidworks_api_help`.

## ADDED Requirements

### Requirement: Structured lookups for methods, interfaces, and enums
The adapter SHALL expose `lookup_api_method` (interface + method name →
signature), `lookup_api_interface` (interface name → all indexed
members), and `lookup_api_enum` (enum name → all indexed values). Each
SHALL indicate no match found, rather than raising, when the name isn't
in the indexed documentation.

#### Scenario: Known method
- **WHEN** `lookup_api_method` is called with an interface/method pair
  present in the indexed documentation
- **THEN** the response includes that method's parameters and return type

#### Scenario: Known interface
- **WHEN** `lookup_api_interface` is called with an indexed interface name
- **THEN** the response includes every indexed member of that interface

#### Scenario: Known enum
- **WHEN** `lookup_api_enum` is called with an indexed enum type name
- **THEN** the response includes every indexed named value

#### Scenario: Unknown name
- **WHEN** any of the three lookups is called with a name absent from the
  indexed documentation
- **THEN** the response indicates no match, not an exception

### Requirement: Related API members can be discovered from a known member
A related-members lookup SHALL, given a known interface or method name,
return other indexed members commonly used alongside it.

#### Scenario: Looking up members related to a known method
- **WHEN** the related-members lookup is called with an indexed method
  name
- **THEN** the response includes other indexed members contextually
  connected to it

### Requirement: Full-text search remains unchanged
`search_solidworks_api_help`'s existing behavior SHALL be unaffected by
these additions.

#### Scenario: Existing full-text search still works
- **WHEN** `search_solidworks_api_help` is called with a keyword query
- **THEN** it returns results exactly as it did before this change
