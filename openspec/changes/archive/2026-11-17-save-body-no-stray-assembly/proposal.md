## Why

Issue #101: after `save_body_as_part` succeeds, an extra unsaved assembly
(`Assem<N>`) is open in SolidWorks, and the reply doesn't mention it. The
part file is written correctly; the assembly is clutter the user has to
close, and it becomes the active document, so the next tool acts on it.

## What Changes

- Before the Save Bodies call, the adapter notes the open documents. After
  it, any document that is new, an assembly and unsaved is closed, and the
  part is made active again.
- The reply's `closed_documents` lists what was closed. Nothing that was
  open before, or that has a file, is touched.

## Capabilities

### Modified Capabilities
- `tools/multibody-part-export`: no document left open behind the call.

## Impact

`adapters/solidworks/io.py` (`save_body_as_part`), the mock adapter, the
tool description, and the live test in `test_live_sw_wave3.py`.
