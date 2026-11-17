## ADDED Requirements

### Requirement: Enum values

`get_api_enum` SHALL return an enum's members and their integer values
from the installed SolidWorks constants type library. Given a member name
instead, it SHALL return the enum that member belongs to, and say which
member matched. Names SHALL match regardless of case. A name that is
neither SHALL be reported as not found, with the reason, rather than
raising.

#### Scenario: An enum by name
- **WHEN** `get_api_enum` is called with `swUnitSystem_e`
- **THEN** the result lists its members with `swUnitSystem_IPS` = 3 and `swUnitSystem_MMGS` = 5

#### Scenario: A member by name
- **WHEN** it is called with `swunitsystem_ips`
- **THEN** the result is `swUnitSystem_e`, with `matched_member` `swUnitSystem_IPS`

#### Scenario: An unknown name
- **WHEN** it is called with a name that is neither an enum nor a member
- **THEN** `found` is false and the note says so

#### Scenario: No constants library
- **WHEN** the constants type library can't be loaded
- **THEN** the index is built without enums, the other lookups still work, and `get_api_enum` says why it has nothing
