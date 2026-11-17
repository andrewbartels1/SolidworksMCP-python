## Context

The catalog pages are hand-written: a description, prerequisites, a
parameter table, a sample call and often response fields per tool. The
generator produced a cruder version and overwrote the hand text, so it
was not run after 2026-11-15. The four harness tests that read its JSON
(`tests/.generated/tool_catalog.json`) skip when the file is missing,
which is always so in CI.

## Decisions

- **The pages are the source; the check keeps them honest.** It parses each
  entry: from its `### \`name\`` heading to the next heading of that level.
  - The parameter table is the one after `**Parameters:**`, rows starting
    `| \`field\` |`.
  - The sample is the first ```json block after `**Sample call:**`.
- **Input model** from the tool function's `input_data` annotation, so the
  sample is validated exactly as a call would be; field names come from the
  model's fields (aliases are not listed).
- **Family pages**: the page is named after the family tag; `server_admin`
  gets `server-admin.md`.
- **Missing entries written from the tool's docstring:**
  - its first line is the entry's description;
  - its `Example input:` is the sample call, where the docstring has one;
  - the table comes from the model's field descriptions, then is reviewed
    by hand.
- **Generator removed** rather than fixed: two sources for one page drift
  again.
