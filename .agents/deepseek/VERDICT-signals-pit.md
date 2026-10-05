===VERDICT START===
# VERDICT: signals-pit — DeepSeek (checker)

**Status:** CHANGES_REQUESTED
**Round:** 1

Checker read-only. All mutations applied to a disposable `git archive HEAD` copy
under `/tmp/sigcheck/`; no worktree file edited. Shipped code == `HEAD`
(commit `41b2455`), which sits on top of `6691d52` (this CHECK request).

## Focus-area results (the five CHECK questions)

1. **Three named mutations** — run against the shipped code, not re-implementations:

   | Mutation | Edit | Result |
   |---|---|---|
   | plain `shift(-1)` (drop gap+same-day checks) | `ml/baseline_labels.py:69-75` | **FAILS** — 4 tests: `test_5min_gap_is_nan`, `test_overnight_gap_is_nan`, `test_symbols_never_mix`, `test_plain_shift_labels_5min_gap` |
   | drop the same-day check (`valid = ok_gap & nxt_ret.notna()`) | `ml/baseline_labels.py:75` | **PASSES — 11/11, zero failures** (blocking finding F1) |
   | split train on `prediction_ts <= cut` | `ml/baseline_labels.py:104` | **FAILS** — 2 tests: `test_purged_split_no_label_leak`, `test_prediction_ts_split_leaks_label` |

2. **Are `test_plain_shift_labels_5min_gap` / `test_prediction_ts_split_leaks_label` vacuous?**
   Partially. Both define an inline *buggy* re-implementation
   (`_forward_labels_plain_shift` `tests/ml/test_baseline_labels.py:140-152`,
   `_purged_split_on_prediction_ts` `:169-174`) and assert that re-implementation is
   buggy — that half is tautological and never mutates the shipped
   `forward_labels`/`purged_split`. The shipped-code half (asserting the *correct*
   function returns NaN / no leak) is real but redundant with
   `test_5min_gap_is_nan` / `test_purged_split_no_label_leak`. Net: the true mutation
   coverage for mutations 1 and 3 comes from the *regular* tests (verified above), not
   from these two "mutation" tests. Non-blocking note N1.

3. **Edge cases** (probed directly against the shipped function):
   - *Duplicate `prediction_ts` for a symbol*: no crash; the earlier duplicate gets NaN
     (gap=0 < tol), the later duplicate labels forward correctly. Safe, untested (N2).
   - *Unsorted input*: the function silently mislabels (all-NaN in my probe) — the
     `[symbol, prediction_ts]` sort is a documented precondition
     (`ml/baseline_labels.py:44-45`) but is neither enforced nor tested (N3).
   - *tz-naive input*: handled — `_eastern_date` treats naive as UTC
     (`ml/baseline_labels.py:29-30`); labelling works. Untested (N4).
   - *DST transition*: correct — `gap = nxt_ts - ts` on tz-aware UTC is true elapsed
     time and `_eastern_date` uses `tz_convert("America/New_York")`, which applies DST.
     No failure mode found.

4. **Script** (`scripts/publish_baseline_signals.py`):
   - Final refit (`:56`) fits on `lab` (all labelled rows). Every labelled row has
     `label_ts <= max(prediction_ts)` because `label_ts` is always some snapshot's
     `prediction_ts` and the global-max snapshot is never labelled. So the refit is
     free of labels observed after the *global* scoring snapshot, matching the
     documented spec. **Pass** (nuance: a symbol whose latest snapshot predates the
     global max shares a model refit on other symbols' later labels — inherent to a
     global model, consistent with the spec).
   - Printed `cut` (`:50`) and the cut `purged_split` uses (`ml/baseline_labels.py:103`)
     are both `lab["prediction_ts"].quantile(0.8)` on the same `lab`. **Identical.**
   - No string-interpolated SQL beyond the fixed column list; `--write` guard intact.

5. **`python3 -m pytest tests/ml -q`** → **48 passed** (matches Claude's report; see N6).

## Blocking findings

- **F1** [`ml/baseline_labels.py:73,75`] The spec's third required mutation — *drop the
  same-day check* — is not covered by any failing test. Replacing
  `valid = ok_gap & same_day & nxt_ret.notna()` with `valid = ok_gap & nxt_ret.notna()`
  yields **11/11 tests passing**. The same-day check (`_eastern_date`) is the exact
  behaviour the Claude tiny fix changed, yet `test_overnight_gap_is_nan` only rejects an
  overnight row via the *gap* check (17.5h ≫ 31min), and
  `test_same_day_uses_us_eastern_date_for_utc_input` exercises the positive path only
  (it still passes with the check deleted). Concrete failure scenario: a future refactor
  or DST/naive-input regression that silently drops the same-day guard ships with a green
  suite. Fix: add a test where two snapshots are ~30 min apart (within tolerance) but on
  different US/Eastern trading dates (e.g. crossing midnight ET) and assert NaN — it must
  fail under the deletion mutation.

## Non-blocking notes

- **N1** [`tests/ml/test_baseline_labels.py:140-174`] The two "mutation" tests re-implement
  the buggy logic inline instead of mutating the shipped code, so their buggy-version
  assertions are self-referential. Not vacuous for the shipped half, but the "red phase"
  wording in the spec is not actually demonstrated by them.
- **N2** Duplicate `prediction_ts` per symbol is handled safely but has no test.
- **N3** [`ml/baseline_labels.py:44-45`] The documented `[symbol, prediction_ts]` sort
  precondition is neither enforced nor tested; unsorted input silently yields NaN/wrong
  labels instead of raising. The script sorts first, so not exploitable today.
- **N4** [`ml/baseline_labels.py:29-30`] tz-naive input is silently treated as UTC;
  correct for the warehouse path but unadvertised in the public docstring example and untested.
- **N5** [`ml/baseline_labels.py:78`] `out.loc[..., "label_ts"] = nxt_ts[valid]` writes
  tz-aware values into a `pd.NaT` (naive) column → pandas `FutureWarning`; will raise in a
  future pandas. Latent breakage (already noted by MiMo).
- **N6** [`.agents/mimo/VERDICT-signals-pit.md:28`] MiMo's self-reported "18/18 passed" for
  `tests/ml` is stale/incorrect — the suite is 48 tests; 18 is merely `test_baseline_labels`
  + 8 others. Consistent with the CHECK's premise that MiMo's verdict is a self-report.

## Checks run

- `python3 -m pytest tests/ml -q` → **48 passed** (64s)
- mutation *plain shift(-1)* → `tests/ml/test_baseline_labels.py` **4 failed**
- mutation *drop same-day check* → **0 failed (11 passed)** ← F1
- mutation *split on `prediction_ts`* → `tests/ml/test_baseline_labels.py` **2 failed**
- edge-case probes (duplicate ts / unsorted / tz-naive / DST) → no crash, behaviour as described above
===VERDICT END===
