# Errors and limits

## Reading an error

Every failed call returns `status: "error"`, a `message`, an `error_type`
and a `hint`; some carry `data` with details. Act on `error_type`:

| `error_type` | What to do |
| --- | --- |
| `no_active_document` | Open or create one (`open_model`, `create_part`), or `activate_document`. |
| `no_active_sketch` | `create_sketch` first. |
| `wrong_document_type` | The active document is the wrong kind (a drawing tool on a part); switch with `activate_document`. |
| `not_found` | A name or path is wrong. List what exists (`list_features`, `list_components`, `list_drawing_views`, `list_open_documents`) and retry with the exact name. |
| `feature_not_built` | SolidWorks accepted the call but built nothing: the sketch isn't closed, the cut misses the body, the depth is wrong. Change the input, don't repeat the call. |
| `not_supported` | The tool can't run yet. Use the one its description names. |
| `circuit_open` | Calls are paused after repeated failures. Fix the cause (for example, close and draw the sketch again), then call `reset_circuit_breaker` with the operation, or wait out the timeout, and retry. |
| `solidworks_unavailable` | SolidWorks closed or crashed. Tell the user; they restart it. |
| `com_member_not_found`, `com_type_mismatch`, `com_wrong_thread` | A server problem, not a modelling one. Stop and tell the user the tool, the arguments and the message. |

Don't retry the same call unchanged: if it failed once with the same input,
it will again.

## Recovering

- `rebuild_model` rebuilds and, when features fail, returns an error whose
  `data.errors` names each failing feature, what it depends on and a `hint`.
- `undo` steps back one or more operations; its reply says whether the
  feature tree changed.
- `suppress_feature` turns off a feature without deleting it;
  `delete_feature` removes it and its dependents.
- `get_model_info` and `list_features` show where the model stands now.

## Tools that can't run yet

40 tools are registered but nothing implements them (support level
`planned`). Their description says "Not available yet"; every call returns
`not_supported`. They are
mostly batch, template, macro-recording and drawing-analysis tools, plus
`tutorial_simple_hole`, `add_dimension`, `create_section_view`, `create_detail_view`,
`update_title_block`, `analyze_geometry`, `get_material_properties` and
`batch_export`. Each description names what to use today.

## Known faults and how to work around them

| Fault | Workaround |
| --- | --- |
| `create_extrusion` and `create_revolve` ignore `sketch_name` (and the revolve `axis_entity`): they use the sketch closed last. | Call them straight after `exit_sketch` on the right sketch; put the revolve axis in that sketch with `add_centerline`. |
| `create_sketch` echoes a `sketch_name` you pass instead of SolidWorks' name. | Don't pass `sketch_name`; use the name in the reply. |
| `pattern_circular` and `mirror_feature` report an error unless the volume grows, so a pattern or mirror of a cut fails. | Pattern or mirror the sketch entities (`sketch_circular_pattern`, `sketch_linear_pattern`, `sketch_mirror`), then cut once. |
| `create_part` ignores `material`; `create_assembly` ignores `components`; `create_drawing` ignores `model_path` and `sheet_format`. | `set_material` after the first feature; `insert_component` for each part; `create_drawing_view` or `generate_drawing_package` for views. |
| `create_technical_drawing` ignores its template, sheet size, title and output path. | `generate_drawing_package` for a complete drawing. |
| `delete_feature`'s message may not mention the dependents it also removed. | `list_features` afterwards. |
| `save_as` replaces an existing file whatever `overwrite` says. | `save_part` or `save_assembly`, which refuse an existing file unless `overwrite` is on. |
| The `export_*` tools take the format from the file extension, not `format_type`. | Name the file with the right extension. |
| `calculate_mass_properties` labels moments of inertia kg·mm², but they are kg·m². | Read them as kg·m². |
| `check_interference` ignores `include_hidden`. | Show the components you want checked. |
| `execute_macro` runs a macro once, whatever `repeat_count` says, and runs only binary `.swp` files. | Call it again for a repeat. |
| `add_mate` can mate only reference planes and axes, by name. | Model parts so their planes line up with the mates you need. |
