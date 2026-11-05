## MODIFIED Requirements

### Requirement: Structured lookups for methods and interfaces
The adapter SHALL expose `lookup_api_method` (interface + method name →
signature) and `lookup_api_interface` (interface name → all indexed
members). An enum-value lookup is not part of this capability yet (issue
#95). Each SHALL indicate no match found, rather than raising, when the name isn't
in the indexed documentation. Names SHALL match regardless of case, as COM
late binding does. A found member SHALL be reported under its real name and
casing from the type library, and the response SHALL say when the caller's
casing differs.

#### Scenario: Known method
- **WHEN** `lookup_api_method` is called with an interface/method pair
  present in the indexed documentation
- **THEN** the response includes that method's parameters (name, type, and
  direction: `in`, `out` or `in_out`), its return type and its description

#### Scenario: Output parameters are marked
- **WHEN** `lookup_api_method` is called for `ISldWorks.OpenDoc6`
- **THEN** the `Errors` and `Warnings` parameters are reported as `in_out`
  and the other four as `in`

#### Scenario: Caller's casing differs
- **WHEN** `lookup_api_method` is called for `IModelDoc2` and
  `ViewZoomToFit2`
- **THEN** the response reports the member as `ViewZoomtofit2` and says
  the casing differs

#### Scenario: Known interface
- **WHEN** `lookup_api_interface` is called with an indexed interface name
- **THEN** the response includes every indexed member of that interface

#### Scenario: Unknown name
- **WHEN** either lookup is called with a name absent from the
  indexed documentation
- **THEN** the response indicates no match, not an exception

## ADDED Requirements

### Requirement: The index comes only from the SolidWorks type library
The docs index SHALL list exactly the interfaces and members in the
registered SolidWorks type library: every dispatch interface, and no member
the type library doesn't have. It SHALL NOT list COM plumbing members
(`QueryInterface`, `AddRef`, `Release`, `GetTypeInfoCount`, `GetTypeInfo`,
`GetIDsOfNames`, `Invoke`) as SolidWorks members. Every lookup response
SHALL say which type library version answered.

#### Scenario: A real member is found
- **WHEN** `lookup_api_method` is called for `IModelDoc2.SaveBMP` on
  SolidWorks 2026
- **THEN** the member is found

#### Scenario: A made-up member is not found
- **WHEN** `lookup_api_method` is called for
  `IModelDoc2.SaveBitmapWithVariableSize` on SolidWorks 2026
- **THEN** the response indicates no match

#### Scenario: Every interface is indexed
- **WHEN** `lookup_api_interface` is called for `IModelDocExtension`
- **THEN** its members are returned, as for any other interface in the
  type library

#### Scenario: Plumbing is not listed
- **WHEN** `lookup_api_interface` is called for `ISldWorks`
- **THEN** neither `QueryInterface` nor `Invoke` is among the members

### Requirement: The index builds without SolidWorks running
Building the docs index SHALL need SolidWorks installed, not running, and
SHALL NOT start, attach to or call SolidWorks. The type library SHALL be
chosen by the year the call requests, else the year the server was started
with (`--year` or configuration), else the newest registered type library.
The year SHALL NOT be guessed from folder names. Responses SHALL report the
year of the type library that answered.

#### Scenario: SolidWorks is closed
- **WHEN** `discover_solidworks_docs` is called on Windows with SolidWorks
  installed but not running
- **THEN** it builds and saves the index from the newest registered type
  library and reports that version

#### Scenario: The response stays small
- **WHEN** `discover_solidworks_docs` succeeds
- **THEN** the response carries a summary, the type library read and the
  saved index file, not the index itself

#### Scenario: Requested year isn't installed
- **WHEN** a year is requested whose type library isn't registered
- **THEN** the response says that version isn't installed and lists the
  versions that are

#### Scenario: Server started with a year that isn't installed
- **WHEN** the server was started with `--year 2025`, only SolidWorks 2026
  is installed, and a lookup asks for no year
- **THEN** the lookup answers from the 2026 type library and reports
  `year` 2026

#### Scenario: VBA references left out on request
- **WHEN** `discover_solidworks_docs` is called with `include_vba` false
- **THEN** the saved index has no VBA references

### Requirement: Lookups reuse the saved index
A lookup SHALL answer from the saved index of the type library it would
read, and SHALL rebuild it only when it is missing, in an older format, or
from a different type library version. An `index_file` the caller names
SHALL be answered from directly. Failing to save a built index SHALL be
reported as an error, not ignored.

#### Scenario: Repeated lookups
- **WHEN** three lookups run in a row, starting with no index on disk
- **THEN** the first reports `index_status` `rebuilt`, the others `ready`,
  and the index is built once

#### Scenario: A newer SolidWorks is installed
- **WHEN** the saved index is from type library 33.0 and the lookup would
  read 34.0
- **THEN** the index is rebuilt from 34.0

### Requirement: Tool descriptions say how to use the lookups
The description of each docs tool, as an MCP client lists it, SHALL say
what the tool needs (SolidWorks installed, not running), that nothing has
to be called first because the first call builds the index, what each
`index_status` value means, that a no-match carries a `note` saying why,
and give one example call. Every input field SHALL have a description.

#### Scenario: An agent reads the lookup tool
- **WHEN** a client lists the tools
- **THEN** `lookup_api_method`'s description names the setup, the
  `index_status` values and the `note` on a no-match, and has an example

### Requirement: Lookups build or replace an out-of-date index themselves
`lookup_api_method`, `lookup_api_interface`, `find_related_api_members`
and `search_solidworks_api_help` SHALL build the index when none exists or
when the existing one was written in an older index format, before
answering. An index in an older format SHALL never be used to answer. When
no index can be built (not Windows, or no SolidWorks type library
registered), the response SHALL say so and how to fix it, rather than
answering from any built-in list of names.

#### Scenario: Index from an older version on disk
- **WHEN** a lookup runs and the only index on disk is in the older format
- **THEN** the index is rebuilt from the type library and the answer comes
  from the rebuilt index

#### Scenario: No type library available
- **WHEN** a lookup runs where no SolidWorks type library is registered
- **THEN** the response indicates no match and says the index could not be
  built because SolidWorks isn't installed here

#### Scenario: The old opt-in is still accepted
- **WHEN** `search_solidworks_api_help` is called with
  `auto_discover_if_missing` set
- **THEN** the call is accepted and behaves as it would without it
