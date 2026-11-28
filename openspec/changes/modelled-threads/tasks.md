## 1. Probe

- [x] 1.1 Probe the Thread feature (die and tap, M10x1.5), the profile
      folder and the profiles' sizes on SolidWorks 2026 (answers in
      design.md)

## 2. Adapter

- [x] 2.1 `adapters/thread_rules.py`: size parsing (metric, inch), coarse or
      fine, depth, runout, the diameter check
- [x] 2.2 `base.py` parameter models and methods; wrappers in
      `circuit_breaker.py` and `connection_pool.py`
- [x] 2.3 `adapters/solidworks/threads.py`: list the profiles' sizes; make
      the thread, measured
- [x] 2.4 `adapters/mock_threads.py`

## 3. Tools

- [x] 3.1 `tools/threads.py`: `list_thread_sizes`, `create_thread`
- [x] 3.2 Register; toolset family; support levels (beta); hints;
      classifier rules; `create_hole`'s description points to them

## 4. Tests

- [x] 4.1 Unit tests mirroring src, 100% coverage
- [x] 4.2 Live test `tests/live/test_live_sw_threads.py`: an M6 rod
      threaded 12 mm, an M6 tapped hole; one refusal each; look at the
      images (passed 2026-11-28: M6 63.8 mm³ over 12 turns, 1/4-20
      89.3 mm³, the internal M6 40.3 mm³ in a 5.0 mm hole)

## 5. Docs

- [x] 5.1 Tool-catalog page, counts, skill workflow, CHANGELOG, queue
- [ ] 5.2 A demo section and GIF once the user has seen it
