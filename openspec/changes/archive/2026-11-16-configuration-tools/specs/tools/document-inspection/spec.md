## MODIFIED Requirements

### Requirement: Every configuration is listed

`list_configurations` SHALL list the name of every configuration of the
active part or assembly, and SHALL report which one is active as `active`.

#### Scenario: A part with two configurations
- **WHEN** a part has the configurations "Default" and "Long"
- **THEN** the reply's `configurations` holds both names and `count` is 2

#### Scenario: The active configuration
- **WHEN** "Long" is active
- **THEN** the reply's `active` is "Long"
