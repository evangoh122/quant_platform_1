# BUILD evidence — BUILD-research-symbols (commodity ETFs as a research/benchmark group)

Builder: dsbuild implementation stage (DeepSeek `deepseek/deepseek-flash`).
Request: `.agents/requests/BUILD-research-symbols.md`.
Owner decision: option **D** of `.agents/requests/SOL-commodity-etfs-advice.txt`
(2026-10-22) — commodity ETFs get daily research coverage (split-adjusted silver
+ corporate actions) **without** entering the trading universe or baseline
signal publication.

- Worktree: `/home/jianj/code/wt-research-syms` (WSL)
- Branch: `feat/research-symbols-commodities` (from `origin/main`)
- Base SHA: `0dc5b1c3e4598a6ea2c3b22f28cac7125da4b123`
- Code+tests commit: `e7904244719ce2ec4feb9ebe6d4d889b19833da6`
  (`feat(data): commodity ETF research group in adjusted silver and corporate actions; fix silver/universe build order`)
- Not pushed. No merge, deploy, warehouse, Spark or ingestion run.

Host boundary: every repository command ran through LF Bash scripts invoked once
as `wsl.exe -d Ubuntu -- bash <path>`; logs are beside each script
(`.agents/run-rsym-{1,2,3,4,5}.agent.log`). No inline `bash -c`, no Windows
wrappers.

## Changes (as committed in `e790424`)

| # | File | Change |
|---|------|--------|
| 1 | `config/research_symbols.yaml` (new) | `groups.commodity_etfs.symbols` with the 10 owner-named ETFs, each with `commodity` and `etf_kind: physical\|futures`; header documents the consumers and guarded non-consumers. |
| 2 | `config/research_symbols.py` (new) | `load_research_symbols(path=None) -> list[str]` (`:157`) delegating to `load_research_registry` (`:105`); `normalize_symbol` (`:73`) validates upper-case ticker shape (`_SYMBOL_RE`, `:35`); `_UniqueKeyLoader` (`:44`) rejects duplicate YAML keys (PyYAML otherwise silently keeps the last); metadata validation (`commodity` non-empty, `etf_kind in ETF_KINDS`, `:30`); trading-universe overlap warns (`load_research_symbols`, `:157`) instead of raising. |
| 3 | `pipelines/run_silver_gold.py` | Registers `research_universe` next to `universe` (`register_research_universe`, `:120`; called from `main`, `:452`); imports the loader at `:35`. |
| 4 | `silver/08_silver_ohlcv_day_adjusted.sql` | `_universe` view (`:122-137`) unions `research_universe` (`:134`) beside ever-in-Gold + SPY/RSP/QQQ; the rest of the split-adjustment pipeline is untouched, so research symbols get the same full daily history and break detection. |
| 5 | `notebooks/refresh_bronze_corporate_actions.py` | New pure `build_universe_sql(fqn, research_symbols=())` (`:176`) and `main` now calls `build_universe_sql(FQN, load_research_symbols())` (`:608`), so USO/UNG reverse splits are fetched although the ETFs are not in `gold_tradable_universe`. Symbols are re-validated by `normalize_symbol` before being quoted into SQL. |
| 6 | `pipelines/run_silver_gold.py` | Ordering fix: `gold_tradable_universe` is now the first step (`STEPS`, `:50-68`) because `silver/08` reads it as its symbol filter. Everything else in `STEPS` / `TARGET_TABLES` is unchanged (asserted by `test_no_step_was_dropped_by_the_reorder`). |
| 7 | `tests/test_research_symbols.py` (new) | Loader contract: config order, 10 symbols, `commodity`/`etf_kind`, disjointness, overlap warning-not-error, duplicate/lowercase/non-string/SQL-breaking symbol/metadata/group rejection, no pandas/duckdb. |
| 8 | `tests/test_research_symbols_pipeline.py` (new) | Production wiring: silver/08 union, corporate-action SQL builder + `main` wiring, step order, and the research-symbols-stay-research guard with named mutations. |
| 9 | `tests/gold/test_gold_log_returns.py` | One line: the existing `main()` wiring test now stubs `register_research_universe` alongside `register_universe` (main registers two views). No assertion changed. |

### Guard (research symbols never reach the model matrix)

`tests/test_research_symbols_pipeline.py::TestSignalsGuard` (`:326`) scans
`silver/`, `gold/`, `pipelines/`, `scripts/`, `notebooks/`, `ml/`, `api/`,
`agent/` for `research_universe` / `load_research_symbols` / `research_symbols`
and allows only `pipelines/run_silver_gold.py`, `silver/08_...sql`,
`notebooks/refresh_bronze_corporate_actions.py` and the two config files. It also
asserts:

- `gold/01_gold_ohlcv_features.sql` filters the minute spine with
  `symbol IN (SELECT symbol FROM universe)` (trading view only) and has no
  research reference (`test_model_matrix_inputs_are_filtered_by_the_trading_universe_only`, `:334`);
- `gold/05_gold_model_features.sql` keeps `gold_ohlcv_features` as its spine and
  has no research reference;
- `scripts/publish_baseline_signals.py` reads `gold_model_features` and has no
  research reference;
- `register_universe` does not load the research group (`:342`).

So `gold_model_features` inputs and published baseline signals remain
trading-universe-only by construction.

## Acceptance environment

- `uv 0.12.23`; acceptance venv outside the worktree (`/tmp/rsym-venv`,
  CPython 3.12.13) created with `uv venv`, then
  `uv pip install -r requirements.txt -r requirements-dev.txt` with `ibapi`
  dropped exactly as CI does, plus `pytest pytest-asyncio pytest-timeout httpx`.
  `tzdata` was added because the uv-managed CPython build has no system
  zoneinfo for the legacy `US/Eastern` key used by
  `tests/ml/test_baseline_labels.py` (CI's system Python uses the distro
  tzdata; environment-only).
- The venv is out of tree because `tests/rag/test_sec_rag_ingest.py` scans `*.py`
  repo-wide without excluding `.venv`; an in-repo venv produces 110 false
  "example.com" hits from site-packages. Round 1 confirmed this and the venv was
  relocated (round 2).
- Logs: `.agents/run-rsym-1.agent.log`, `-2`, `-3`, `-4`, `-5`.

## Acceptance results

Exact CI command, run with the acceptance venv:

```text
$ /tmp/rsym-venv/bin/python -m pytest -q -m "not spark and not lakebase and not databricks"
2983 passed, 70 skipped, 24 deselected, 46 warnings in 381.08s
```

Same command with pyspark blocked by a stub package (`/tmp/.../pyspark/__init__.py`
raising `ModuleNotFoundError("No module named 'pyspark'")`) placed first on
`PYTHONPATH`:

```text
2983 passed, 70 skipped, 24 deselected, 46 warnings in 372.40s
```

(round 3 log; round 2 shows the same green stub run and one flaky failure in the
normal run — see "Environment findings".)

Targeted new/adjacent tests (round 2): `294 passed, 6 skipped`.

Other acceptance checks:

```text
$ git grep -n "import pandas\|import duckdb" -- config/research_symbols.py
(no output — NO_PANDAS_DUCKDB)          # run against the committed tree in round 4

$ grep -rIl $'\r' <all changed files>
LF_OK

$ git status --porcelain      # before the commit
 M notebooks/refresh_bronze_corporate_actions.py
 M pipelines/run_silver_gold.py
 M silver/08_silver_ohlcv_day_adjusted.sql
 M tests/gold/test_gold_log_returns.py
?? config/research_symbols.py
?? config/research_symbols.yaml
?? tests/test_research_symbols.py
?? tests/test_research_symbols_pipeline.py
WORKTREE_SCOPE_OK
```

## Old-behavior proof (`git archive` of `origin/main`, isolated under /tmp)

Copied only the two new test files into `/tmp/rsym-proofs/old` (never a recursive
worktree copy) and ran them against the pre-change tree:

```text
tests/test_research_symbols.py            -> 1 error (no config.research_symbols module)
tests/test_research_symbols_pipeline.py   -> 9 failed, 11 passed
  FAILED ...::TestAdjustedSilverResearchUnion::test_view_unions_research_symbols
  FAILED ...::TestAdjustedSilverResearchUnion::test_view_keeps_gold_universe_and_benchmarks
  FAILED ...::TestCorporateActionUniverse::test_builder_includes_gold_universe_benchmarks_and_research
  FAILED ...::TestPipelineOrder::test_gold_universe_is_built_before_adjusted_silver
  (plus the builder/wiring tests that require build_universe_sql)
```

Control: the same tests pass from a `git archive` copy of `e790424`
(`46 passed in 1.90s`), so the failures above are the old behavior, not the
archive location.

## Mutation proofs (`git archive` of `e790424` under /tmp, one copy per mutation)

| Mutation | Expected failing test | Observed |
|---|---|---|
| M1: delete every `research_universe` line from `silver/08_silver_ohlcv_day_adjusted.sql` | `TestAdjustedSilverResearchUnion::test_view_unions_research_symbols` | 2 failed, 2 passed (`test_view_unions_research_symbols`, `test_view_keeps_gold_universe_and_benchmarks`) |
| M2: move the `gold_tradable_universe` step back to the end of `STEPS` (pre-fix order) | `TestPipelineOrder::test_gold_universe_is_built_before_adjusted_silver` | 1 failed, 3 passed (message: built after `silver_ohlcv_day_adjusted`) |
| M3: append `AND symbol IN (SELECT symbol FROM research_universe)` to `gold/01_gold_ohlcv_features.sql` | `TestSignalsGuard::test_only_the_allowlisted_files_mention_research` | 2 failed, 4 passed (also `test_model_matrix_inputs_are_filtered_by_the_trading_universe_only`) |

Round 5 ended with `PROOFS_OK`; worktree HEAD and status were unchanged by the
proofs.

## Environment findings (not caused by this change)

1. `tests/api/test_public_demo_security.py` rate-limit tests are flaky: the
   limiter uses `int(time.monotonic()) // 60` fixed windows, so a 60-request
   loop that crosses a minute boundary never hits the limit. Round 2: normal run
   failed `test_no_cf_header_leftmost_xff_used`, the identical pyspark-stub run
   passed. Round 3 isolated runs: run 1 failed
   `test_different_leftmost_ips_get_separate_buckets`, runs 2–3 passed. Round 3
   normal and stub full runs were both fully green (2983 passed each).
   Untouched by this change (`api/main.py`, `tests/api/**` not modified).
2. The uv-managed CPython 3.12.13 has no `US/Eastern` zoneinfo without the
   `tzdata` package; round 1's 12 `tests/ml/test_baseline_labels.py` failures
   were all `ZoneInfoNotFoundError: 'No time zone found with key US/Eastern'`
   and disappeared after installing `tzdata`.
3. In-repo `.venv` breaks the repo-wide placeholder scan
   (`tests/rag/test_sec_rag_ingest.py:2737`); the acceptance venv lives in
   `/tmp`. The in-repo artifact created in round 1 was removed explicitly.

## Non-goals honoured

- No change to `config/universe.yaml`, `gold_tradable_universe`, `gold/01`,
  `gold/05`, `scripts/publish_baseline_signals.py`, `frontend/**`, `api/**`.
- No minute-bar ingestion, no `notebooks/refresh_bronze_equities.py` change, no
  perp universe, no new dependency, no pandas/DuckDB in new code, no Spark or
  Databricks execution, no data/table writes, no push.

## Notes / follow-ups for the owner

- The research group reaches `silver_ohlcv_day_adjusted` and
  `bronze_corporate_actions` only; it is not a research view in Gold yet (the
  Sol advice also suggests a separate Gold research view for gap/coverage work —
  deliberately out of this request's scope).
- `silver/08` relies on the `research_universe` temp view registered by
  `pipelines/run_silver_gold.py`; running that SQL standalone now requires the
  view (same contract as the existing `universe` view).
- Distribution-only adjustment remains out of scope: splits are adjusted,
  distributions are not, so ETF ex-dividend gaps stay visible in raw returns.

## Verdict path

Independent validation: `.agents/requests/VALIDATE-research-symbols.md`
(DeepSeek) against commit `e7904244719ce2ec4feb9ebe6d4d889b19833da6` (code and
tests); this evidence file is committed separately and does not alter code.
