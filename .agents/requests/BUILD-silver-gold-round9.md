# BUILD-REQUEST: silver-gold — ROUND 9 (CodeRabbit findings)

**Branch:** `slice/silver-gold` · **Builder:** DeepSeek · **Validators:** Claude, then Codex

Round 8 verified live: 40,983 rows = 40,983 NY trading sessions (the old 43,345 contained
2,362 split-session rows); all four `*_available_ts` populated; exact invariant 0 violations.
Keep it. These findings come from CodeRabbit's review of PR #8 and were confirmed by the
coordinator.

## 1. `ON` is stored as `TRUE` (data corruption, confirmed live)

`config/universe.yaml:50` lists `- ON` unquoted. YAML parses `ON` as boolean `True`, and the
loader turns it into the string `"TRUE"`. Live: `silver_ohlcv` has **4,158 rows with
`symbol = 'TRUE'`** and none for `ON` (ON Semiconductor).

- Quote every ticker in `config/universe.yaml` (`- "ON"`), and make the loader **reject
  non-string entries** rather than coercing them, so this cannot recur (YAML also turns
  `YES`, `NO`, `OFF`, `Y`, `N`, `TRUE`, `FALSE`, `NULL` into non-strings).
- Check `config/tickers.yaml` and its loader for the same problem. Do not reformat that
  12,400-line file wholesale; fix the loader and quote only affected entries.
- Repair the data: every `silver_*` and `gold_*` row with `symbol = 'TRUE'` must become
  `'ON'` (or be rebuilt). Paste before/after counts for `TRUE` and `ON` in each table.

## 2. The sentiment dictionary is mislabelled

`data/sentiment_dict/lm_word_lists.json` says it is the *Loughran-McDonald (2020)*
dictionary, but its list sizes do not match the published lists (e.g. uncertainty 2,756
here vs ~297 published; litigious 103 vs ~903). `gold_sec_features` sentiment is
therefore labelled as an academic standard it is not.

Do one of these, and say which in your verdict:
- **(a)** replace it with the real Loughran-McDonald master-dictionary word lists, if you
  can obtain them, with their real provenance and licence note; or
- **(b)** if you cannot obtain them, **relabel honestly**: rename the file and its
  `source` field to say what it is (e.g. "custom financial sentiment lists, partly derived
  from Loughran-McDonald"), and update every docstring/comment/doc that claims LM.

Do **not** invent or reconstruct LM lists from memory and label them as LM.
Re-run `gold_sec_features` if the dictionary changes; paste the row count (expect 128).

## 3. Build-script fixes (`pipelines/run_silver_gold.py`)

- `:86` — do not swallow `TRUNCATE` failures; let them fail the run (or log and re-raise).
- `:107` — stop calling `str.format` on raw SQL text; SQL containing `{` `}` (e.g. map or
  JSON literals) will break. Use explicit placeholder replacement.

## Constraints

Do not touch `agent/`, `db/`, `api/`, `frontend/`, `ml/`, `conftest.py`, `pytest.ini`,
`requirements*.txt`, `.agents/dispatch.sh`. Re-run the round-8 invariant after the repair
and paste it. **Commit your work.** Write `.agents/deepseek/VERDICT-silver-gold-round9.md`.
