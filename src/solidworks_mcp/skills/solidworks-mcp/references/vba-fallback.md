# When to write VBA instead

Use a direct tool whenever one exists: it reports what it did, checks the
result, and can be undone. Fall back to VBA only when:

- no tool makes the feature: a shell (`generate_vba_part_modeling`), or a
  mate between faces or edges (`generate_vba_assembly_mates`);
- a tool doesn't expose an option you need: extrusion end conditions beyond
  the ones `create_extrusion` takes (`generate_vba_extrusion`), or revolve
  options (`generate_vba_revolve`);
- the user wants a macro to keep and run themselves.

## What the VBA tools do and don't do

The `generate_vba_*` tools only write macro text. They read nothing from
SolidWorks and change nothing. The macro comes back in `vba_code` with
`usage_instructions`; the user pastes it into the SolidWorks VBA editor
(Alt+F11) and runs it.

`execute_macro` runs a binary `.swp` macro file that already exists. It
refuses VBA source text, so it can't run what the `generate_vba_*` tools
return. A macro it runs must not wait for the user (no message boxes or
forms), or the call hangs, and its changes can't be undone from here.

After the user runs a macro, read the model back (`get_model_info`,
`list_features`, `verify_model`) before going on: nothing reports what the
macro did.

To look up a SolidWorks API call while writing VBA, use
`lookup_api_method`, `lookup_api_interface` or `search_solidworks_api_help`.
