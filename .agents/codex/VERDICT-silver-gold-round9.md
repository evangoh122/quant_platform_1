# VERDICT: silver-gold rounds 8-9 — Codex
CHANGES_REQUESTED

1. The matrix invariant is still incomplete for every source column group.

   - It correctly fails the build when a detected violation exists: violations raise `RuntimeError`, and both normal gold builds and `--check` invoke the invariant ([pipelines/run_silver_gold.py:244](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:244), [pipelines/run_silver_gold.py:282](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:282), [pipelines/run_silver_gold.py:317](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:317)).
   - However, there is no OHLCV “features imply `ohlcv_available_ts`” check. Because `GREATEST` ignores NULLs, a matrix row with populated OHLCV features but a NULL OHLCV timestamp can pass ([pipelines/run_silver_gold.py:216](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:216)).
   - The SEC check omits `sec_material_event`, so a row where that is the only populated SEC feature can have NULL `sec_available_ts` and pass ([pipelines/run_silver_gold.py:232](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:232)).
   - Options and COT do enumerate every source feature stored in the matrix ([pipelines/run_silver_gold.py:224](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:224), [pipelines/run_silver_gold.py:237](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:237)).

2. `tickers.yaml` validation is inconsistent across its public loader paths.

   - `get_all_tickers()` and `get_tickers_by_groups()` reject non-string YAML values ([config/tickers.py:55](/home/jianj/code/qp1-sg/config/tickers.py:55), [config/tickers.py:77](/home/jianj/code/qp1-sg/config/tickers.py:77)).
   - `get_tickers_by_group()` returns raw entries without calling `_validate_ticker`, so YAML boolean/null values remain accepted through that loader path ([config/tickers.py:95](/home/jianj/code/qp1-sg/config/tickers.py:95)).
   - `load_universe()` correctly rejects non-strings ([config/universe.py:23](/home/jianj/code/qp1-sg/config/universe.py:23)).
   - Independent parsing found no remaining non-string ticker/symbol entries in either current YAML file; `ON` is quoted at [config/universe.yaml:56](/home/jianj/code/qp1-sg/config/universe.yaml:56).

3. The dictionary is still represented as Loughran–McDonald in active application code.

   Although the JSON now explicitly says it is non-canonical, the service module calls it “the financial-specific Loughran-McDonald dictionary,” and its class/loader/counting docstrings repeat that attribution ([api/services/sentiment.py:2](/home/jianj/code/qp1-sg/api/services/sentiment.py:2), [api/services/sentiment.py:38](/home/jianj/code/qp1-sg/api/services/sentiment.py:38), [api/services/sentiment.py:51](/home/jianj/code/qp1-sg/api/services/sentiment.py:51), [api/services/sentiment.py:131](/home/jianj/code/qp1-sg/api/services/sentiment.py:131)). Those claims should describe the bundled lists as custom/partly derived, consistent with the JSON metadata.

Reconciliation review:

- The new spine groups bars by `DATE(convert_timezone('UTC', 'America/New_York', feature_ts))`, which is DST-aware and correctly avoids splitting one New York session at UTC midnight ([gold/05_gold_model_features.sql:44](/home/jianj/code/qp1-sg/gold/05_gold_model_features.sql:44)).
- A late bar that changes a session’s maximum availability deletes the old prediction row before merging the replacement ([gold/05_gold_model_features.sql:52](/home/jianj/code/qp1-sg/gold/05_gold_model_features.sql:52)).
- The delete is constrained by symbol and New York date, so ordinary late-bar reconciliation does not delete another symbol/session. One boundary caveat remains: the target session is inferred from `prediction_ts`, not the originating `feature_ts`; a bar ending exactly at local midnight would classify its target row into the following date ([gold/05_gold_model_features.sql:57](/home/jianj/code/qp1-sg/gold/05_gold_model_features.sql:57)). Current U.S. equity sessions do not normally reach that boundary.

Earlier fixes remain intact:

- Trailing OHLCV windows: [gold/01_gold_ohlcv_features.sql:35](/home/jianj/code/qp1-sg/gold/01_gold_ohlcv_features.sql:35).
- Minute availability plus interval: [gold/01_gold_ohlcv_features.sql:22](/home/jianj/code/qp1-sg/gold/01_gold_ohlcv_features.sql:22).
- Options availability at DST-aware session close plus buffer: [gold/02_gold_options_features.sql:69](/home/jianj/code/qp1-sg/gold/02_gold_options_features.sql:69).
- COT full 52-report gate: [gold/04_gold_cot_features.sql:64](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:64), [gold/04_gold_cot_features.sql:107](/home/jianj/code/qp1-sg/gold/04_gold_cot_features.sql:107).
- `is_stale` remains scoped to each ingest batch: [silver/03_silver_options_quotes.sql:50](/home/jianj/code/qp1-sg/silver/03_silver_options_quotes.sql:50).
- TRUNCATE failures are re-raised, and raw SQL no longer uses `str.format`: [pipelines/run_silver_gold.py:90](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:90), [pipelines/run_silver_gold.py:136](/home/jianj/code/qp1-sg/pipelines/run_silver_gold.py:136).

Tests: `19 passed in 1.06s` using the requested command.

No files were written.
