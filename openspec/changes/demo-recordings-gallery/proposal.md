## Why

The demo GIFs are slideshows: one still of SolidWorks per evidence step, each
held for the same four seconds. Nothing moves, so a viewer can't see a feature
appear or a drawing fill in, and the stills are scaled down to 1100 px. The
maintainer wants a gallery of high-resolution recordings where motion plays
at a real frame rate.

## What Changes

- A recorder for live demos (`tests/live/recorder.py`). With
  `SW_DEMO_RECORD` set, a background thread grabs the SolidWorks window's
  screen pixels up to `SW_DEMO_RECORD_FPS` times a second (default 12) and
  keeps a frame only when the picture changed. It never calls SolidWorks:
  it copies screen pixels (`ImageGrab`), so it cannot add COM load or touch
  the selection.
- `evidence()` also records its caption, with the time, so each recorded
  frame can carry the caption that was current when it was taken.
- `tests/scripts/make_demo_gif.py --recording` builds one high-resolution GIF
  per test (default 1280 px) from a recording. Each frame is shown for as
  long as it was really on screen, so motion plays at the recorded rate and a
  still stretch is one frame; stills are capped (default 3 s) so pacing waits
  don't drag.
- `live_demo.ps1 -Record` turns the recorder on and builds the recording
  GIFs as well as the existing stills.
- A demo gallery page in the docs, linked from the README, showing every
  demo GIF with what it proves and the test or script that made it.

Out of scope: video formats (MP4/WebM), and moving the camera (spinning the
model) during a demo, which would mean extra COM calls.

No change to the server, the adapters or the tools.

## Capabilities

### New Capabilities

- `docs/demo-recordings`: live demos can be recorded as high-resolution
  GIFs with a frame rate that follows the motion, and shown in a gallery.

### Modified Capabilities

None.

## Impact

- New: `tests/live/recorder.py`, `docs/demos.md`.
- Changed: `tests/live/evidence.py`, `tests/live/conftest.py`,
  `tests/scripts/make_demo_gif.py`, `tests/scripts/live_demo.ps1`,
  `mkdocs.yml`, `README.md`.
- Recordings are written under the capture directory in `recording/<test>/`;
  only the built GIFs are meant to be committed.
