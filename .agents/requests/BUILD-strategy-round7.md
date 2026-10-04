# BUILD: strategy round 7 (MiMo)

DeepSeek check4 returned CHANGES_REQUESTED (`.agents/deepseek/VERDICT-strategy-check4.md`).
Round 6 fixed sign flips but **regressed same-side partial reductions**: `+0.4 → +0.2` is
throttled at the cap instead of landing at +0.2 in one day.

## Fix: `strategies/backtest.py:~95-125`
Define the legs by direction relative to zero, per name:
- `close_leg`: the part of the move that goes toward 0, ending at 0 at most. Always free.
  - Same side, `|cur| < |prev|`: `close_leg = cur - prev`, no open leg.
  - Flip, or `cur == 0`: `close_leg = -prev`.
- `open_leg`: the part that goes away from 0. Capped at `cap_frac * adv / book_capital`.
  - From 0, or same side with `|cur| > |prev|`: `open_leg = cur - prev`.
  - Flip: `open_leg = cur`.

## Tests, which stop the ping-pong
1. A unit test for `[0.4]*20 + [0.2]*8`, with a cap well below 0.2. The weight on the first
   reduction day is exactly 0.2.
2. **Property test** over 500 random target sequences (seeded): random signs, magnitudes,
   zeros, flips, and NaN-then-ffilled ADV. For every name and day, with `out` the realised
   weight:
   - (a) **Never overshoot:** `out[t]` lies between `out[t-1]` and `target[t]`, inclusive.
   - (b) **Free moves toward zero:** if `target[t]` is between 0 and `out[t-1]`, inclusive
     (a same-side reduction or exit), then `out[t] == target[t]`.
   - (c) **Flips close fully:** if the sign flips, then `out[t]` has the new sign or is 0, and
     `|out[t]| <= cap`.
   - (d) **Increases are capped:** `|out[t]| - |out[t-1]| <= cap + 1e-12` whenever
     `sign(out[t]) == sign(out[t-1])`, or `out[t-1] == 0`.
3. Show in /tmp copies:
   - The property test FAILS on the round-6 code (current HEAD) and on the round-5 code (75e0e7d).
   - It PASSES on your fix.

Run:
- `python3 -m pytest -q tests/strategies tests/ml`;
- `PYTHONPATH=/tmp/nopyspark python3 -m pytest -q tests/strategies`.

Add `CHANGELOG[6]` rows. LF line endings only. Don't touch `.agents/dispatch.sh` or
`strategies/results/`. Commit. Write `.agents/mimo/VERDICT-strategy-round7.md`.
