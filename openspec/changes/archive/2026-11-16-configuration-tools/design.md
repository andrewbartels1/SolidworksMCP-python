## Context

`list_configurations` reads the names (fixed in 2.0.0 to read
`IConfiguration.Name` as a property). `set_dimension`'s real adapter calls
`GetDimension2(0).SetSystemValue3(value_m, 1, None)`: 1 is
`swSetValue_InThisConfiguration`, so it already changes only the active
configuration. `suppress_feature` calls `EditSuppress2`/`EditUnsuppress2`
on the selected feature, which also act on the active configuration.

COM members, from the type library index:

| Need | Member |
| --- | --- |
| Create | `IConfigurationManager.AddConfiguration2(Name, Comment, AlternateName, Options, ParentConfigName, Description, Rebuild)` |
| Activate | `IModelDoc2.ShowConfiguration2(Name)` |
| Delete | `IModelDoc2.DeleteConfiguration2(Name)` |
| Active name | `IConfigurationManager.ActiveConfiguration` → `IConfiguration.Name` |
| Scoped value | `IDimension.SetSystemValue3(NewValue, WhichConfigurations, Config_names)` |
| Scoped suppression | `IFeature.SetSuppression2(SuppressionState, Config_opt, Config_names)` |

## Goals / Non-Goals

**Goals:**
- Variants of one model in a few calls, with every change's scope stated.
- Today's calls keep doing what they do: `this` is the default.

**Non-Goals:**
- Design tables (Excel), configuration-specific materials or custom
  properties, assembly component configurations (`set_component_state`
  covers component suppression).
- Renaming a configuration.

## Decisions

### 1. One `configurations` input, three forms

`configurations: Literal["this", "all"] | list[str] = "this"`. The adapter
maps it to the enum both COM calls share in meaning:
`this` → 1, `all` → 2, a list → 3 with the names as a string array
(`VARIANT(VT_ARRAY | VT_BSTR, names)`), and `None`/`Missing` for the names
otherwise. A list is checked against the model's configuration names
first thing in the adapter's COM operation, before anything changes, and
the error ("No configuration named ...") is classified `invalid_input`.
(Changed while building it: the adapter already reads the names, so the
tool doesn't read them a second time.) For `this`, `set_dimension` keeps
the proven `SystemValue` write; `all` passes the names array too, as
`None` marshals as `VT_NULL`, which SolidWorks rejects for array arguments.

### 2. Suppression keeps today's path for `this`

For `this`, `suppress_feature` keeps `EditSuppress2`/`EditUnsuppress2`,
which are proven live. For `all` or a list, it uses
`IFeature.SetSuppression2` with `swSuppressFeature` (0) or
`swUnSuppressFeature` (1), then rebuilds. The reply's `configurations`
names where it applied.

### 3. Creating doesn't switch unless asked

`AddConfiguration2` makes the new configuration active. When `activate` is
off, the adapter shows the previous configuration again, so creating a
configuration doesn't change what the next call acts on. Options: 0 (no
special behaviour); a `parent` uses `ParentConfigName` for a derived
configuration.

### 4. Delete guards in the tool

The tool reads the active configuration and the list first and refuses
the active or the only configuration with `invalid_input`; SolidWorks
returns False in those cases without a reason.

## Risks / Trade-offs

- [`SetSystemValue3`'s names array marshals wrongly under late binding] →
  the live bundle sets a value in a named configuration and reads it back
  in each; if it fails, the adapter activates each named configuration and
  sets `this`, then restores the active one.
- [Switching configurations rebuilds a large assembly slowly] → each
  activation goes through the settle pause; no extra waits are added.
- [Agents forget the scope] → the default is the same as before, and every
  reply names the configurations changed.
