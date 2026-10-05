===VERDICT START===
# VERDICT: signals-pit-r2 — DeepSeek (checker)

**Status:** APPROVED
**Round:** 2

Checker read-only. All three mutations applied to a disposable `git archive HEAD`
copy under `/tmp/sigcheck2/`; no worktree file edited. Shipped code == `HEAD`
(`5edacd6`), which carries round-2 commit `f013fe2` verbatim for `ml/` and
`tests/` (`git diff f013fe2 HEAD -- ml/ tests/` → empty).

## Round-2 focus (the four CHECK questions)

1. **Three named mutations, re-run against shipped code — each must fail:**

   | Mutation | Edit | Result |
   |---|---|---|
   | plain `shift(-1)` (drop gap + same-day) | `ml/baseline_labels.py:73-79` | **5 failed** (`test_5min_gap_is_nan`, `test_overnight_gap_is_nan`, `test_symbols_never_mix`, `test_midnight_straddle_is_nan`, `test_duplicate_prediction_ts_earlier_gets_nan`) |
   | drop the same-day check (`valid = ok_gap & nxt_ret.notna()`) | `ml/baseline_labels.py:77-79` | **1 failed** (`test_midnight_straddle_is_nan`) — F1 closed |
   | split train on `prediction_ts <= cut` | `ml/baseline_labels.py:108` | **1 failed** (`test_purged_split_no_label_leak`) |

   F1 was the round-1 blocker (drop-same-day passed 11/11). It now fails exactly
   on the new `test_midnight_straddle_is_nan` — two snapshots 30 min apart
   straddling midnight ET (03:45→04:15 UTC) correctly rejected only because of the
   same-day guard.

2. **N1 inline re-implementations gone** — `grep -rn
   '_forward_labels_plain_shift|_purged_split_on_prediction_ts'` → **not found**
   anywhere in the repo. The two tautological "mutation" tests are removed; the
   surviving same-day/shuffle tests assert shipped-code behaviour only.

3. **Internal sort keeps results aligned to the caller's index** — probe with a
   shuffled, non-default index (`[5,2,9,7,1]`) verified each label lands on the row
   matching its own snapshot's true next-snapshot return, i.e. index-aligned, not
   position-aligned. `AAPL idx=5` → 1.0, `AAPL idx=2` → 0.0 (from −0.01), all
   group-wise expected labels match `out.loc[i,'label']`. **PASS.** (Output frame is
   returned in sorted order, not original order; `purged_split` and the publish
   script both operate via index-aligned masks, so no caller is affected.)

4. **`python3 -m pytest tests/ml -q`** → **50 passed** (79s, matches Claude's 50).

## Blocking findings

None.

## Non-blocking notes

- **N5** [`ml/baseline_labels.py:82`] Round-1 pandas `FutureWarning`
  (tz-aware `label_ts` into a naive `pd.NaT` column) is still present — out of
  round-2 scope, unchanged behaviour. Latent future-pandas breakage only.
- **N-order** [`ml/baseline_labels.py:63-65`] `forward_labels` now returns the frame
  in `[symbol, prediction_ts]` sorted order rather than preserving input order.
  Correct for its single caller, but worth documenting as a behavioural change vs
  round 1 (docstring updated; callers relying on positional order would need a
  `.reindex(df.index)`).
- **N-dup** [`tests/ml/test_baseline_labels.py:207`] Duplicate-`prediction_ts` test
  relies on a stable sort keeping the two equal-key rows in insertion order; that is
  guaranteed by `kind="stable"` but is not independently asserted.
- **N4** [`tests/ml/test_baseline_labels.py:225`] tz-naive-as-UTC now has a test, but
  the public docstring example still uses a tz-aware timestamp, so the naive→UTC
  fallback remains unadvertised.

## Checks run

- `python3 -m pytest tests/ml -q` → **50 passed**
- mutation *plain shift(-1)* → `tests/ml/test_baseline_labels.py` **5 failed**
- mutation *drop same-day check* → `tests/ml/test_baseline_labels.py` **1 failed** (F1)
- mutation *split on `prediction_ts`* → `tests/ml/test_baseline_labels.py` **1 failed**
- `grep` for N1 re-implementations → **not found**
- index-alignment probe (shuffled non-default index) → **PASS**
===VERDICT END===
