## Why

Configurations are how SolidWorks users make size variants of one part (a
bolt in five lengths, a bracket with and without a slot). An agent can
only list them today (`list_configurations`). It can't make one, switch to
one, or change a dimension or suppress a feature in one configuration
only. Worse, `set_dimension` already changes the active configuration only
(it passes `swSetValue_InThisConfiguration` to `SetSystemValue3`), and
`suppress_feature` acts on the active one, and neither says so, so an
agent editing a part with configurations gets results it can't predict.
The planned `manage_design_table` is removed by the honest-tool-list change
(it needs Excel on the machine); these tools give agents the same variants
without it.

## What Changes

- **`create_configuration`**: adds a configuration to the active part or
  assembly, by name, optionally as a derived (child) configuration of
  another, with a description; it can be made active at once.
- **`activate_configuration`**: makes a configuration active and rebuilds.
- **`delete_configuration`**: deletes a configuration that isn't active.
- **`set_dimension` gains `configurations`**: `this` (the default, today's
  behaviour, now stated), `all`, or a list of names.
- **`suppress_feature` gains `configurations`**: the same choices, through
  `IFeature.SetSuppression2`.
- **`list_configurations`** also reports which configuration is active.
- The descriptions of `set_dimension`, `suppress_feature` and
  `get_dimension` say which configuration they act on.

## Capabilities

### New Capabilities

- `tools/configurations`: creating, activating and deleting
  configurations, and scoping dimension and suppression changes to them.

### Modified Capabilities

- `tools/document-inspection`: `list_configurations` reports the active
  configuration.

## Impact

- **COM and adapter code, all on the connect thread inside
  `_handle_com_operation`:**
  - `IConfigurationManager.AddConfiguration2`,
    `IModelDoc2.ShowConfiguration2`, `DeleteConfiguration2`;
  - `IConfigurationManager.ActiveConfiguration` (its `Name` is a property,
    runbook "properties are still properties");
  - `IDimension.SetSystemValue3` with `WhichConfigurations` 1, 2 or 3 and
    the names array;
  - `IFeature.SetSuppression2` replaces `EditSuppress2`/`EditUnsuppress2`
    when a scope other than `this` is given.
  - Three new adapter methods, and `configurations` on two existing ones,
    through `base.py`, `circuit_breaker.py`, `connection_pool.py` and
    `mock_adapter.py`.
- **Tools:** `modeling.py` (`set_dimension`, `suppress_feature`, three new
  tools), `file_management.py` (`list_configurations`), `tool_hints.py`,
  `support_levels.py`.
- **Docs:** catalog pages, the agent skill's note on configurations,
  CHANGELOG, progress bars.
- No issue is filed; this is queue item 13.
- **Depends on the honest-tool-list change (queue item 10)**, merged
  first: it sets the verb list and ran the design-table probe. The probe
  (2026-11-14) showed design tables don't work through COM on this
  install, so `manage_design_table` was removed; this change builds
  configurations without Excel.
