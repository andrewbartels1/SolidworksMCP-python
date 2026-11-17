# Notes

## The tool list before this change (task 1.2, 2026-11-16)

Measured with `python -m solidworks_mcp.progress.tool_list_size` on the
mock adapter, before any toolset or mode was applied: 135 tools, 215 KB,
about 55,000 tokens (bytes / 4) sent on every turn.

| Family | Tools |
| --- | ---: |
| modeling | 38 |
| file_management | 20 |
| sketching | 19 |
| drawing | 13 |
| vba_generation | 10 |
| engineering_data | 8 |
| drawing_automation | 7 |
| export | 6 |
| docs_discovery | 5 |
| analysis | 4 |
| automation, drawing_analysis, macro_recording, server_admin, template_management | 1 each |

`core` alone is 96 tools and two thirds of the size: modelling and
sketching are most of the list, so the toolsets save less than the search
mode (4 tools, about 900 tokens).
