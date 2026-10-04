# VERDICT: strategy round 7 — MiMo
**Status:** APPROVED
**Round:** 7

## Blocking findings

None.

## Non-blocking notes

- The round-6 code (`same_side = sign(prev)*sign(cur) > 0`) routed same-side
  reductions (`|cur| < |prev|`) into `open_leg`, throttling them at the ADV cap
  instead of executing freely as close legs. This is the regression DeepSeek
  check4 identified.
- Fix: close_leg = `dw` when same-side and `|cur| < |prev|` (magnitude shrinks),
  close_leg = `-prev` on sign flip or exit, close_leg = `0` from zero or same-side
  increase. Open leg = `dw - close_leg`, capped as before.
- Property test (500 random sequences, seed 42): 0 violations on the fix.
  Round-6 code: 0 violations (same-side reductions are capped but stay between
  prev and target, so overshoot invariant passes; the unit test catches the
  regression specifically). Round-5 code (75e0e7d): 171 violations (flip exceeds
  cap — the original bug that round 6 fixed).

## Checks run

```
$ wsl python3 -m pytest -q tests/strategies tests/ml
78 passed, 34 warnings in 84.14s

$ wsl env PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/strategies
41 passed, 16 warnings in 8.26s

$ wsl python3 /tmp/reduction_test_versions.py
Day 20 (first reduction day):
  Round 6: 0.3800 (expected 0.2000, got throttled)
  Fix:     0.2000 (expected 0.2000)
Round 6 day20 == 0.2? False  (expected False)
Fix day20 == 0.2?     True  (expected True)

$ wsl python3 /tmp/property_test_versions.py
Round 6 (HEAD 1d956ea): 0 violations
Round 5 (75e0e7d): 171 violations
Round 7 (fix): 0 violations
```

## Commits

- `d6c5f70` fix(strategy): round 7 — same-side partial reduction ADV cap regression