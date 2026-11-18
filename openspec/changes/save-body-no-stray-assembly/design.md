## Decisions

- **Clean up after, not change the call.** `CreateSaveBodyFeature`
  takes `(Bodies, FilePaths, AssemName, ConsumeBody, CopyCustomProperty)`;
  no argument turns the assembly off (checked in the type library), and
  the cause can't be probed without SolidWorks. Closing what the call left
  works whatever triggers it.
- **Only what is safe to close:** new since the call (by title), an
  assembly, and no file (`GetPathName` empty). Closing it loses nothing.
- **The part becomes active again** with `ActivateDoc3`, so the next tool
  acts on it.
