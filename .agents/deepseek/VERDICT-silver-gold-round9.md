# VERDICT: silver-gold round 9 (CodeRabbit findings) — DeepSeek
**Status:** APPROVED
**Round:** 9

Implements all three findings in `.agents/requests/BUILD-silver-gold-round9.md`: the
`ON` → `TRUE` YAML corruption (config + loaders + live data repair), the mislabelled
sentiment dictionary (option **b** — honest relabel), and the two build-script fixes in
`pipelines/run_silver_gold.py`. Committed on `slice/silver-gold`.

---

## 1. `ON` stored as `TRUE` — DONE (config + loaders + live repair)

**Config.** `config/universe.yaml` now quotes every ticker (`- "ON"` etc.) and documents
why. `config/universe.py::load_universe` rejects any non-string symbol with a `ValueError`
instead of `str()`-coercing it, so `ON`/`YES`/`NO`/`OFF`/`Y`/`N`/`TRUE`/`FALSE`/`NULL`
can no longer silently become booleans.

**`config/tickers.yaml`.** Checked by re-parsing the file: **0 non-string tickers** out of
12,400 raw entries — the PyYAML `dump` that generated it already quoted the boolean-shaped
tickers, and the ticker `ON` is not present in the whole-market list at all (the corrupted
`ON` came from `universe.yaml`, not `tickers.yaml`). No entries needed quoting. The loader
`config/tickers.py` was still hardened: `_validate_ticker` rejects non-string entries in
`get_all_tickers` / `get_tickers_by_groups` (the two functions that previously did
`str(t)`), so a future `- ON` cannot coerce to `"True"`.

**Live data repair.** Every `silver_*` / `gold_*` row whose symbol column held `'TRUE'`
now holds `'ON'`. Derived hash keys were recomputed with the build's own expressions
(verified 0 mismatches against the stored values before mutating, so the recomputation is
provably consistent). Before → after:

| table.column | TRUE (before) | TRUE (after) | ON (after) |
| :--- | ---: | ---: | ---: |
| `silver_ohlcv.symbol` | 4,158 | 0 | 4,158 |
| `silver_ohlcv_quarantine_batch.symbol` | 0 | 0 | 0 |
| `silver_options_quotes.underlying` | 0 | 0 | 0 |
| `silver_options_trades.underlying` | 0 | 0 | 0 |
| `silver_sec_sections.ticker` | 0 | 0 | 0 |
| `silver_sec_entities.ticker` | 0 | 0 | 0 |
| `gold_ohlcv_features.symbol` | 4,158 | 0 | 4,158 |
| `gold_options_features.symbol` | 277 | 0 | 277 |
| `gold_sec_features.ticker` | 0 | 0 | 0 |
| `gold_model_features.symbol` | 22 | 0 | 22 |

`silver_cot_positions` / `gold_cot_features` have no symbol column (asset-regime level),
so they are unaffected. Row counts are preserved (UPDATE, not rebuild).

## 2. Sentiment dictionary relabelled — DONE (option b)

Could not obtain the canonical Loughran-McDonald master lists in this environment, and the
request forbids reconstructing them from memory. Took option **(b)**:

- `data/sentiment_dict/lm_word_lists.json` — `source`/`reference`/`note` now say it is
  *"Custom financial sentiment word lists (partly derived from Loughran-McDonald)"* and
  explicitly state it is **NOT** the canonical master dictionary (with the observed size
  discrepancies quoted).
- `gold/gold_sec_features.py` — docstring no longer calls it "the Loughran-McDonald scorer"
  / "LM dictionary".
- `ontology/metric_definitions.yaml` — `sentiment_score.dictionary` is now
  `"custom (partly derived from Loughran-McDonald)"`.

The word lists themselves are unchanged (only the mislabel is fixed), so `gold_sec_features`
re-ran to **128 rows** (unchanged, as expected).

## 3. Build-script fixes — DONE

- `pipelines/run_silver_gold.py:96` — `truncate_targets` now logs and **re-raises** on a
  `TRUNCATE` failure instead of swallowing it (a silent skip could previously leave a
  `--truncate` run building on un-truncated tables).
- `pipelines/run_silver_gold.py:137` — `run_step` no longer calls `str.format` on raw SQL;
  it uses explicit `.replace("{date_start}", …)` / `.replace("{date_end}", …)`, so SQL
  containing `{`/`}` (map or JSON literals) cannot break the format call.

## Round-8 invariant re-run (after repair) — PASS

```
universe: 39 symbols
=== availability invariant ===
  options info_ts >= session close:            0 violating rows
  cot info_ts >= report_date:                  0 violating rows
  ohlcv minute info_ts >= event_ts + 1 minute: 0 violating rows
=== matrix availability invariant ===
  all source availability <= prediction_ts:    0 violating rows
  options features imply options_available_ts: 0 violating rows
  sec features imply sec_available_ts:         0 violating rows
  cot features imply cot_available_ts:         0 violating rows
```

## Blocking findings

None.

## Non-blocking notes

- **`lm_word_lists.json` was not renamed.** The request's option (b) suggested renaming
  the file, but `api/services/sentiment.py:28` hardcodes the path
  `data/sentiment_dict/lm_word_lists.json`, and `api/` is explicitly out of scope this
  round ("Do not touch … `api/`"). Renaming would silently break the scorer (empty
  dictionary → zero sentiment) and the `tests/rag/test_sentiment.py` suite. The `source`
  field and every in-scope doc/comment that claimed LM are relabelled; the LM claims in
  `api/services/sentiment.py` and `api/models/schemas.py` remain and need a follow-up in
  the api lane.
- **`bronze_ohlcv` (and other bronze sources) still carry `symbol='TRUE'`.** The repair is
  scoped to `silver_*`/`gold_*` as requested. Consequence: a `--truncate` rebuild run
  *before* bronze is re-ingested would drop ON's silver data, because the now-corrected
  universe contains `ON` and no longer matches bronze's `'TRUE'` rows (the MERGE would
  insert nothing). Bronze re-ingestion is out of scope here; flagging for the coordinator.
- `.agents/dispatch.sh` has a working-tree mode change (100755 → 100644), a WSL/Windows
  filesystem artifact present before this round; left uncommitted.

## Checks run

- `python3 -m pytest tests/test_tickers_config.py tests/rag/test_sentiment.py tests/gold/test_pit_leakage.py --noconftest -q` → **59 passed**
- `python3 -m py_compile config/universe.py config/tickers.py pipelines/run_silver_gold.py gold/gold_sec_features.py` → **pass (exit 0)**
- Live `load_universe()` → 39 symbols; `"ON"` present, `"TRUE"` absent
- Live `tickers.yaml` re-parse → 12,400 entries, 0 non-string
- Live data repair → before/after counts pasted above
- Live `gold/gold_sec_features.py` re-run → **128 rows**
- Live `python3 pipelines/run_silver_gold.py --check` → round-8 invariant 4×0 (pasted above)
