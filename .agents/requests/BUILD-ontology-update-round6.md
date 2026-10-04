# BUILD ontology round 6 (author: Codex gpt-5.6-sol, at the owner's explicit request)

Owner: "get codex sol to update the ontology". You (Codex) edit `ontology/*.yaml`, `ontology/README.md` and
`tests/test_ontology.py` directly. Branch slice/ontology-update (main already merged in by Claude, b5b5ea7).

Sandbox notes: you cannot commit (worktree git dir is read-only to you) and cannot write `.agents/`. Just edit files;
Claude commits. Print your report between `===REPORT START===` and `===REPORT END===` on stdout.
Never invent columns: every table/column you add must be verified from SQL/code on the branch named below
(read with `git show <branch>:<path>`; all branches are local refs in this repo).

## Bring the ontology in line with the in-flight lanes
1. **Corporate actions** (`slice/corporate-actions`): `bronze_corporate_actions` (key symbol, ex_date, source;
   sources massive (primary) / yfinance (fallback); split_ratio = new/old shares; information_available_ts = 09:30
   America/New_York on ex_date, in UTC), `silver_ohlcv_day_adjusted` (adj_open/high/low/close/vwap/volume,
   cumulative_split_ratio, price_adjustment_factor; availability = 16:30 NY bar close in UTC), `data_quality_breaks`
   (reason codes incl. split_source_mismatch if present on the branch). Business terms: "split-adjusted price",
   "corporate action", "reverse split". Join hint: daily bars → adjusted bars; any return/vol/momentum metric must
   be defined on adjusted prices, and say so in metric_definitions (bronze_ohlcv_day is UNADJUSTED).
   NOTE round 5 on that branch (Massive source, source precedence) may still be in progress — describe precedence
   only if it exists on the branch; otherwise document yfinance and mark massive as "planned".
2. **NL analytics v1** (`slice/nl-contracts`, package `analytics_nl/`, `docs/NL1_PROPOSED_SERVING_VIEWS.md`,
   `source_schemas_v1.yaml`): the 9 metrics incl. implied_volatility (iv_atm) and put_call_ratio — ensure every NL1
   metric has an entry in metric_definitions.yaml with the same name/formula/grain/source table, and that the
   proposed serving views are registered in table_semantics as `status: proposed` (not live).
3. **SEC RAG coverage** (`slice/rag-coverage`): gold_sec_coverage, sec_ingest_log (and sec_cik_mapping_log only if
   a writer exists on the branch). Coverage universe = gold_tradable_universe (300/day, 557 ever).
4. **Knowledge graph** (`slice/rag-kg`): `gold_sec_kg_build_runs` manifest table; keep node/edge names synced to
   `sec_kg/model.py` enums (the existing enum-sync test + snapshot must still pass — refresh the snapshot only if the
   enums changed on that branch, and say so).
5. Anything on main (merged since round 5) missing from table_semantics: check every CREATE TABLE in silver/, gold/,
   notebooks/refresh_bronze_*.py, pipelines/ on main.

## Tests
Extend tests/test_ontology.py: every table referenced anywhere resolves; `status: proposed` tables cannot be the
source of a live metric; metrics on price returns reference the adjusted table (or are explicitly flagged unadjusted).
Run `python -m pytest tests/test_ontology.py -q` and the full `python -m pytest -q --ignore=tests/lakebase`; report counts.

## Report
List every table/metric/term added or changed with the branch:path:line it was verified against, and anything you
could not verify (left out, not guessed).
