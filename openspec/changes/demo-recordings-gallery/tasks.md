## 1. Recorder

- [x] 1.1 `tests/live/recorder.py`: a thread that grabs the SolidWorks
      window rectangle with `PIL.ImageGrab` (no SolidWorks call), compares
      each grab with the last kept frame on a small greyscale copy, and saves
      changed frames as `recording/<test>/<NNNNN>-<ms>.png`
- [x] 1.2 `evidence()` records its caption panel and time to the running
      recording; caption rendering is shared with the stills
- [x] 1.3 `tests/live/conftest.py`: an autouse fixture starts and stops the
      recorder per test when `SW_DEMO_RECORD` is set

## 2. GIF builder

- [x] 2.1 `make_demo_gif.py --recording`: frame durations from the recorded
      times (at least one frame interval, at most `--max-hold`), the current
      caption beneath each frame, `--width` 1280 by default; writes
      `<test>-motion.gif`
- [x] 2.2 Check it offline on a synthetic recording (a still stretch, a fast
      stretch, two captions)

## 3. Runner and gallery

- [x] 3.1 `live_demo.ps1 -Record [-Speed n]` sets `SW_DEMO_RECORD`, counts
      down 10 s before recording, shortens the holds, and builds the
      recording GIFs (`<test>-motion.gif`)
- [x] 3.2 `docs/demos.md` gallery page in the mkdocs nav: per demo the
      GIF, what it proves, the prompt (real for the README demo, a
      labelled example for the tests), the tool calls (all 58 from the
      README demo's transcript) and the source; `mkdocs build --strict`
      passes
- [x] 3.3 README Demos section shows the GIFs in a grid, each linked to
      its gallery entry, then points to the gallery page

## 4. Live

- [x] 4.1 Record the README demo with the maintainer; check the GIF's size
      and how it reads
