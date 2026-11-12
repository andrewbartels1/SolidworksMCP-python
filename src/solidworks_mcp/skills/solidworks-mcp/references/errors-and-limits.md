# Errors and limits

## Reading an error

Every failed call returns `status: "error"`, a `message`, an `error_type`
and a `hint`; some carry `data` with details. Act on `error_type`:

| `error_type` | What to do |
| --- | --- |
| `no_active_document` | Open or create one (`open_model`, `create_part`), or `activate_document`. |
| `no_active_sketch` | `create_sketch` first. |
| `wrong_document_type` | The active document is the wrong kind (a drawing tool on a part); switch with `activate_document`. |
| `invalid_input` | An argument is wrong, or is one a tool no longer takes; the message says what to send instead. Fix the call. |
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
  `delete_feature` removes it and its dependents. Ask the user before
  deleting: a sketch takes every feature built from it with it, and the
  reply's `warning` names what else went.
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
| `add_mate` can't mate edges or vertices, only planes, axes and faces. | Mate the faces that meet at the edge. |
| `pack_and_go_assembly` copies the files as saved on disk; unsaved changes in open parts are left out, and its `warning` names those parts. | Save the assembly and its parts first, then pack. |
| `compare_drawing_versions`: SolidWorks writes a different file every time it saves, so two saves of an unchanged drawing still differ. | Treat "identical" as proof nothing changed; treat "different" as "may have changed", and check with `list_drawing_views`. |
