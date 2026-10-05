===VERDICT START===
# VERDICT: signals-pit-r3 — DeepSeek (checker)

**Status:** APPROVED
**Round:** 3

Checker read-only. All mutations applied to disposable `git archive HEAD` copies
under `/tmp/{sigcheck3,m1_shift,m2_sameday,m3_split,m4_refit_all}`; no worktree
file edited. Shipped code == `HEAD` (`c8b3cde`), which carries round-3 commit
`c3543d2` verbatim for `ml/`, `scripts/`, `tests/` (archive copies diffed
byte-identical to `HEAD`).

## Round-3 focus (the four CHECK questions)

1. **Script computes the scoring rows BEFORE the refit, refits on `refit_rows(...)`**
   `scripts/publish_baseline_signals.py:55-59` — `latest` (the per-symbol latest
   snapshot, filtered `>= 2026-09-01`) is built at :55-56, *then* `refit =
   refit_rows(lab, latest.prediction_ts)` at :57, then the final `m.fit` runs on
   `refit` (not `lab`) at :59. The same `latest` object is later scored at :60-63.
   The old `m.fit(prepare_features(lab, FEATS)..., lab.label...)` (all-labelled
   refit) is gone. **PASS.**

2. **Comments/docstring match the code**
   `ml/baseline_labels.py:113-138` `refit_rows` docstring says "earliest scoring
   snapshot", "`cutoff = scoring_ts.min()`", "subset of *lab* with `label_ts <=
   cutoff`" — all three match the implementation at :137-138 exactly.
   `scripts/publish_baseline_signals.py:16-19` (module docstring) and :53-54
   (inline comment) both state "`label_ts <= the earliest scoring snapshot`", matching
   the `refit_rows` call. The stale round-2 NOTE block ("only rows with label_ts <=
   the scoring snapshot time…") is removed (`grep` → not found). **PASS.**

3. **Three earlier mutations still fail (re-run against shipped code):**

   | Mutation | Edit | Result |
   |---|---|---|
   | plain `shift(-1)` (drop gap+same-day) | `ml/baseline_labels.py:79` | **5 failed** (`test_5min_gap_is_nan`, `test_overnight_gap_is_nan`, `test_symbols_never_mix`, `test_midnight_straddle_is_nan`, `test_duplicate_prediction_ts_earlier_gets_nan`) |
   | drop same-day check (`valid = ok_gap & nxt_ret.notna()`) | `ml/baseline_labels.py:79` | **1 failed** (`test_midnight_straddle_is_nan`) — F1 still closed |
   | split train on `prediction_ts <= cut` | `ml/baseline_labels.py:108` | **1 failed** (`test_purged_split_no_label_leak`) |

   Round-3 regression mutation (the new finding's proof) also fails as required:

   | Mutation | Edit | Result |
   |---|---|---|
   | `refit_rows` returns all of `lab` (`cutoff = scoring_ts.max()`) | `ml/baseline_labels.py:137` | **1 failed** (`test_refit_rows_staggered_symbols`) |

4. **`python3 -m pytest tests/ml -q`** → **51 passed** (69.7s; matches MiMo's 51).

## Blocking findings

None.

## Non-blocking notes

- **Edge / trade-off (the requested question).** The earliest-cutoff rule is
  PIT-correct but has a real trade-off: the cutoff is the *minimum* scoring
  snapshot, so **one stale symbol pulls the refit window back to its own old
  timestamp and discards every label observed after it.** Probe: with a stale
  symbol whose latest snapshot sits at 2026-09-01 01:00 next to symbols spanning
  to 2026-09-21, the refit set shrank from **1958 labelled rows to 6**. The final
  model is then trained on pre-cutoff (potentially month-old) data even though the
  scored rows are recent. This is the correct PIT behaviour, not a leak — but a
  data-quality hazard worth surfacing (a single dead/one-shot symbol degrades the
  refit for everyone). **Non-blocking**, per the request's criterion.
- **Can the refit become empty?** Yes, in one narrow case: the labelled history
  begins at/after the `2026-09-01` floor *and* the earliest-scoring symbol has no
  valid forward label (e.g. a single-snapshot symbol at exactly the floor), so
  `label_ts.min() > cutoff`. When that happens `m.fit` on the empty `refit` raises
  `ValueError` (scikit-learn "0 samples"/single-class), i.e. it **fails loudly, not
  silently** — and it crashes at `:59` *before* the `--write` gate at `:66`, so no
  bad signals are published. Therefore **non-blocking**, but a cheap `if refit.empty
  or refit.label.nunique() < 2: sys.exit(...)` guard would turn a mid-script crash
  into an explicit, diagnosable stop.
- **N5** [`ml/baseline_labels.py:82`] Pre-existing pandas `FutureWarning` writing
  tz-aware `label_ts` into a naive `pd.NaT` column is unchanged from rounds 1-2 and
  out of scope.

## Checks run

- `python3 -m pytest tests/ml -q` → **51 passed** (69.67s)
- mutation *plain shift(-1)* → `tests/ml/test_baseline_labels.py` **5 failed**
- mutation *drop same-day check* → `tests/ml/test_baseline_labels.py` **1 failed** (F1)
- mutation *split on `prediction_ts`* → `tests/ml/test_baseline_labels.py` **1 failed**
- mutation *`refit_rows` uses `max` (returns all of lab)* → `tests/ml/test_baseline_labels.py` **1 failed**
- `grep` for stale "NOTE: only rows with label_ts" → **not found**
- edge probes (`/tmp/sigcheck3/probe_edge.py`, `probe_empty.py`) → trade-off & empty-refit
  behaviour as described above
===VERDICT END===
