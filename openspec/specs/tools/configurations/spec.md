# tools/configurations Specification

## Purpose
An agent makes, switches and deletes configurations, and changes a
dimension or a feature's suppression in the configurations it names, so
one model can hold several variants.
## Requirements
### Requirement: Create a configuration
`create_configuration` SHALL take `name`, and optionally `parent` (an
existing configuration, making the new one derived from it),
`description`, and `activate` (default off). It SHALL add the
configuration to the active part or assembly and reply with its name and
whether it is active.

#### Scenario: A long variant
- **WHEN** a part has only `Default` and `create_configuration` is called
  with `name` `Long`
- **THEN** `list_configurations` lists `Default` and `Long`, and `Default`
  is still active

#### Scenario: A name already used
- **WHEN** `name` is `Default`
- **THEN** the call fails with `invalid_input` naming the existing
  configuration, and nothing is added

### Requirement: Activate a configuration
`activate_configuration` SHALL take `name`, make it the active
configuration, rebuild, and reply with the active name.

#### Scenario: Switching and back
- **WHEN** `Long` is activated, then `Default`
- **THEN** each reply names the configuration asked for, and
  `get_model_info` reports it as active

#### Scenario: An unknown name
- **WHEN** `name` is not a configuration of the model
- **THEN** the call fails with `invalid_input` listing the configurations

### Requirement: Delete a configuration
`delete_configuration` SHALL take `name` and delete that configuration. It
SHALL fail with `invalid_input` when `name` is the active configuration or
the only one.

#### Scenario: Deleting the active one
- **WHEN** `Long` is active and `delete_configuration` is called with `Long`
- **THEN** the call fails, says to activate another configuration first,
  and `Long` still exists

### Requirement: Dimension and suppression changes name their configurations
`set_dimension` and `suppress_feature` SHALL take `configurations`: `this`
(the default: the active configuration only), `all`, or a list of
configuration names. The change SHALL apply to exactly those
configurations, and the reply SHALL name them.

#### Scenario: A length in one variant
- **WHEN** `Long` is active and `set_dimension` sets `D1@Boss-Extrude1` to
  80 with `configurations` `this`
- **THEN** in `Long` the dimension is 80, and after activating `Default`
  it is still its old value

#### Scenario: A feature suppressed everywhere
- **WHEN** `suppress_feature` suppresses `Fillet1` with `configurations`
  `all`
- **THEN** `Fillet1` is suppressed in `Default` and in `Long`

#### Scenario: A named configuration that doesn't exist
- **WHEN** `configurations` is `["Short"]` and there is no `Short`
- **THEN** the call fails with `invalid_input` listing the configurations,
  and nothing changes

