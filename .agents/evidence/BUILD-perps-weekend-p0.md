# BUILD-perps-weekend-p0 — implementation evidence (DeepSeek dsbuild)

- **Request:** `.agents/requests/BUILD-perps-weekend-p0.md`
- **Branch:** `feat/perps-weekend-p0` (base `origin/main` = `0dc5b1c3e4598a6ea2c3b22f28cac7125da4b123`)
- **Code commit:** `0a06b20d29c2daa254d8bfd86f474966d2e9005d`
  (`feat(perps): weekend perp universe, NYSE weekend calendar, history probe and plan (P0)`)
- **Head to validate:** the SHA in the BUILD DONE line (this evidence file is
  committed on top of the code commit).
- **Environment:** WSL Ubuntu; `uv 0.13.4` provisioned under
  `/tmp/opencode/uvtool` (not on PATH), acceptance venv
  `/tmp/opencode/perps-p0-venv` (CPython 3.12.13, pytest 9.1.1). CI-parity
  requirement files drop `ibapi` and the `-r` include exactly as
  `.github/workflows/ci.yml:41-52` does. `tzdata` was added to the venv because
  the uv standalone CPython lacks legacy `US/Eastern` aliases; the affected
  test is pre-existing and untouched (proof in §5). No pandas/duckdb in new
  code; no network in tests; no live Databricks.
- **Line endings:** all new files verified LF (`grep -qU $'\r'` clean on all
  16 committed files).
- **Not pushed.** No merge, deployment or shared-table write.

---

## 1. Deliverables

| # | Deliverable | Files |
|---|---|---|
| 1 | Perp universe + typed loader | `config/perp_universe.yaml` (byte-identical to `.agents/requests/perp_universe.yaml`, `cmp` clean), `config/perp_universe.py` |
| 2 | Ticker sanity (report only) | `scripts/perps/check_universe.py` |
| 3 | Static NYSE calendar + pure window functions | `config/xnys_holidays.yaml`, `config/market_calendar.py` |
| 4 | History probe (dry-run default) | `scripts/perps/probe_history.py` |
| 5 | Plan + architecture diagram | `docs/data/PERPS_WEEKEND_PLAN.md`, `docs/data/perps_architecture.html` |
| — | Tests + fixtures | `tests/perps/*.py`, `tests/fixtures/perps/*` |

### 1.1 Perp universe loader

- `config/perp_universe.py:411` `load_perp_universe(path=None)`; env override
  `PERP_UNIVERSE_YAML`.
- Strict validation: required `version` (`:318` `_parse_document`), unique
  tickers, `symbol == "<dex>:<TICKER>"` (regex at `:50`, company parser at
  `:243`), venue allowlist (`hyperliquid`, `binance_usdm`), dex allowlist
  (`xyz`, `para`, `io`), tier allowlist, mandatory `BTCUSDT`/`ETHUSDT`
  controls, unique control symbols, unknown keys rejected.
- Real file loads **78 companies + 2 controls** (`python -m config.perp_universe`).
- A permissive `xyz-NVDA` separator is rejected (`PerpUniverseError`); the
  mutation proof in §4 kills a relaxed loader.

### 1.2 Ticker sanity (`check_universe.py`)

- `scripts/perps/check_universe.py:346` CLI; report-only, exit 0 even with
  suspects, never edits the config.
- Reads `config/universe.yaml`, the whole-market `config/tickers.yaml` with its
  inline descriptions (`:95`), and offline SEC CIK files (`:151`:
  `config/sec_cik_overrides.yaml` + `tests/rag/fixtures/sec/company_tickers.json`).
- Classifies ETF/fund/preferred from groups and descriptions (`:180`), plus
  `unmapped` and `not_in_repo_universe`. `--cik-map` accepts a full offline
  `company_tickers.json` snapshot; `--json` writes the machine-readable report.
- Observed output (acceptance §3): 78 checked; **BOT = fund**, **STRC =
  preferred**, **KSTR = ETF+fund**; 73 tickers have no CIK in the *offline*
  files (only 5 of the 78 are in the sparse checked-in fixtures). `BIRD`,
  `CBRS`, `SHAZ` are in the unmapped list. This is a report, not an SEC
  conclusion; the owner decides.

### 1.3 NYSE calendar

- `config/xnys_holidays.yaml` is generated (`python -m
  config.market_calendar --write`) and drift-checked (`--check`). Coverage
  2000-01-01..2035-12-31; 342 full closures (332 rule-derived + 10 ad-hoc) and
  78 early closes. Rules are cited in the YAML header (NYSE Rule 7.2 and NYSE
  trading hours); ad-hoc closures (9/11, Hurricane Sandy, national days of
  mourning) carry announcement citations and are not rule-derived.
- `config/market_calendar.py:511` `last_close_before`, `:534`
  `next_open_after`, `:557` `weekend_window` (UTC in/out, `zoneinfo`
  DST-correct); `:579` `check_calendar_file`; `:635` `render_calendar_yaml`.
- Calendar tests cover Good Friday (start Thursday 16:00 ET), Labor Day (end
  Tuesday 09:30 ET), both DST boundaries, day-after-Thanksgiving 13:00,
  Christmas Eve 13:00, observed July 4 Friday, Saturday New Year's,
  Juneteenth 2022+, and ad-hoc closures.

### 1.4 History probe

- `scripts/perps/probe_history.py`: dry-run by default, `--live` required for
  network; ≤ 2 req/s (`RateLimiter` at `:392`), retries/backoff with
  `Retry-After` (`HttpClient` at `:414`).
- Hyperliquid: `candleSnapshot` 1h/1d and `fundingHistory`, paged by
  `startTime` in `--coarse-days` windows (`find_first_hyperliquid` at `:500`).
- Binance controls: monthly archive listing then first daily archive for
  klines 1h, fundingRate and metrics (`probe_binance` at `:549`).
- Pure parsers/fixtures: `parse_candles` (`:287`), `parse_funding` (`:312`),
  `earliest_timestamp` (`:337`), `parse_binance_listing` (`:359`).
- Rich/dry-run plan: `plan_requests` (`:213`) → **246 planned requests**
  (78 × 3 Hyperliquid streams + 2 × 6 Binance listings).
- OI limitation documented in `OPEN_INTEREST_NOTE` (`:81`): public API is
  current-only; options are forward snapshots (recommended), S3 archive
  backfill under owner approval, or a clearly labelled candle proxy.
- **Live probe not run** (request: coordinator runs it); `--dry-run` made zero
  network calls. The live run writes `docs/data/perps_history_probe.json` and
  `docs/data/perps_history_probe.md`.

### 1.5 Plan and architecture

- `docs/data/PERPS_WEEKEND_PLAN.md`: sources/endpoints/limits (§2), weekend
  window definition and edge cases (§2/§3), Bronze/Silver/Gold schemas (§4),
  provider-symbol bridge to the KG security dimension (§5), PIT invariants
  (§6), PR slices P1–P6 (§7), OI options (§8), risks (§9), reproduction (§10).
- `docs/data/perps_architecture.html`: self-contained HTML + inline SVG per
  the architecture-diagram skill (dark palette, JetBrains Mono, legend outside
  all boundaries, export toolbar, all planned components dashed). Includes the
  P0 lane, sources, ingestion jobs, Bronze/Silver/Gold tables, PIT baselines,
  controls, security bridge, research and owner gate.

## 2. Tests

`tests/perps/` — **63 passed** in the acceptance venv (20.40s):

| File | Focus |
|---|---|
| `test_perp_universe.py` (24) | real 78-company load (`:37`), duplicate ticker (`:79`), bad `xyz-NVDA` (`:90`), missing controls (`:114`), version/selected_at/dex/tier/unknown-field/alternates/negative numbers, env override |
| `test_market_calendar.py` (20) | Good Friday (`:37`), Labor Day (`:46`), DST spring (`:60`) / fall (`:71`), Thanksgiving early close (`:82`), static-vs-rule drift (`:138`), YAML coverage/citations (`:142`), strict boundary semantics, out-of-coverage, ad-hoc closures |
| `test_probe_parsing.py` (14) | candle/funding fixture parsing (`:28`, `:57`), earliest timestamp (`:72`), Binance XML/HTML listing (`:87`), 246-request plan (`:111`), dry-run zero network (`:137`), live orchestration with a fake client (`:185`), rate cap, Markdown |
| `test_check_universe.py` (5) | ETF/preferred/fund flags, expected unmapped suspects, report-only (no removals), custom `--cik-map` |

Fixtures: `tests/fixtures/perps/hyperliquid_candle_snapshot.json`,
`hyperliquid_funding_history.json`, `binance_vision_monthly_listing.xml`,
`binance_vision_daily_listing.html`.

Expectations are asserted against fixed dates/timestamps and the production
loaders; no validation or calendar logic is copied into tests.

## 3. Acceptance runs (final SHA `0a06b20`)

### 3.1 venv and CI-parity install

```text
$ uv venv /tmp/opencode/perps-p0-venv                 # CPython 3.12.13
$ uv pip install --python .../bin/python -r /tmp/opencode/req.txt -r /tmp/opencode/req-dev.txt
Resolved 227 packages in 1.10s
Prepared 227 packages in 1m 11s
Installed 227 packages in 1.65s
$ uv pip install --python .../bin/python tzdata pytest pytest-asyncio httpx
$ .../bin/python -c "import pyspark"
ModuleNotFoundError: No module named 'pyspark'
```

`req.txt`/`req-dev.txt` are the CI-style copies with `ibapi` and the `-r`
include removed. `tzdata` is an environment-only addition (see §5); it is not
added to the repository requirements.

### 3.2 Exact CI command — plain

```text
$ /tmp/opencode/perps-p0-venv/bin/python -m pytest -q -m "not spark and not lakebase and not databricks"
3000 passed, 70 skipped, 24 deselected, 46 warnings in 424.75s (0:07:04)
```

### 3.3 Exact CI command — pyspark blocked

Stub: `/tmp/opencode/ci-parity/pyspark-stub/pyspark/__init__.py` raises
`ModuleNotFoundError("No module named 'pyspark'")`, first on `PYTHONPATH`.

```text
$ PYTHONPATH=/tmp/opencode/ci-parity/pyspark-stub .../python -m pytest -q -m "not spark and not lakebase and not databricks"
3000 passed, 70 skipped, 24 deselected, 46 warnings in 436.28s (0:07:16)
```

The venv has no pyspark installed; the stub run proves no test requires it.
The 70 skips are the suite's pre-existing marker skips (`spark`/`lakebase`/
`databricks`/`network`), identical on the base tree.

### 3.4 Probe dry-run

```text
$ .../python scripts/perps/probe_history.py --dry-run
mode: dry-run (no network; pass --live to probe)
targets: 78 equity perps + 2 Binance controls
planned requests: 246 (Hyperliquid requests are the first page of a startTime-paged stream)
...
planned lines: 246
rc=0
```

`test_dry_run_makes_zero_network_calls` additionally monkeypatches
`urllib.request.urlopen` to raise; it is never called.

### 3.5 Ticker check

```text
$ .../python scripts/perps/check_universe.py
rc=0
Companies: 78; controls: BTCUSDT, ETHUSDT
Checked: 78 tickers; suspects: 73
| BOT  | xyz:BOT  | fund       | RoboStrategy, Inc. Common Stock (closed_end_fund_equity) |
| STRC | xyz:STRC | preferred  | Strategy Inc Variable Rate Series A Perpetual Stretch Preferred Stock |
| KSTR | xyz:KSTR | etf, fund  | KraneShares SSE STAR Market 50 Index ETF |
```

### 3.6 Calendar and forbidden imports

```text
$ python -m config.market_calendar --check
.../config/xnys_holidays.yaml: OK (rules match static calendar)
$ python -m config.market_calendar --summary
coverage 2000-01-01..2035-12-31; 342 full closures (10 ad-hoc), 78 early closes
$ grep -rn "import pandas\|import duckdb" config/perp_universe.py config/market_calendar.py scripts/perps tests/perps
(none)
$ cmp .agents/requests/perp_universe.yaml config/perp_universe.yaml
(identical)
```

## 4. Proofs (isolated `git archive` trees under `/tmp/opencode/proofs`)

### P1. Old behaviour — new tests fail on `origin/main`

Tree: `git archive origin/main`, with only `tests/perps/*.py` and
`tests/fixtures/perps` copied in (no new source).

```text
$ pytest -q tests/perps
E   ModuleNotFoundError: No module named 'config.perp_universe'
ERROR tests/perps/test_check_universe.py
ERROR tests/perps/test_market_calendar.py
ERROR tests/perps/test_perp_universe.py
ERROR tests/perps/test_probe_parsing.py
4 errors in 0.67s
```

### P2. Mutation — drop Good Friday from the holiday table

Tree: `git archive 0a06b20`; remove the 36 `name: "Good Friday"` entries
(36 → 0) from `config/xnys_holidays.yaml`.

```text
$ pytest -q tests/perps/test_market_calendar.py
FAILED test_market_calendar.py::test_good_friday_window_starts_thursday_close
FAILED test_market_calendar.py::test_static_calendar_matches_rule_derivation
FAILED test_market_calendar.py::test_calendar_yaml_covers_range_and_cites_rules
3 failed, 17 passed in 2.94s
```

The Good Friday test now sees Friday 2026-04-03 as a session (start 16:00
instead of Thursday), and the static/rule consistency check reports the 36
missing dates.

### P3. Mutation — accept `xyz-NVDA` symbols

Tree: `git archive 0a06b20`; relax `config/perp_universe.py:50` from
`(?P<dex>[a-z0-9]+):` to `(?P<dex>[a-z0-9]+)[:-]`.

```text
$ pytest -q tests/perps/test_perp_universe.py
FAILED test_perp_universe.py::test_rejects_bad_symbol_with_dash
E   Failed: DID NOT RAISE PerpUniverseError
1 failed, 23 passed in 5.12s
```

The mutated loader really accepts `xyz-NVDA` for NVDA; the test kills it.

### P4. Pre-existing tzdata failure (not caused by this change)

The first venv run (before `tzdata`) had 11 failures, all in the untouched
`tests/ml/test_baseline_labels.py`, all `pd.Timestamp(..., tz="US/Eastern")`
→ `ZoneInfoNotFoundError` / `No module named 'tzdata'`. Uninstalling `tzdata`
and running the same file from a clean `git archive origin/main` extraction
reproduces exactly:

```text
$ git archive origin/main | tar -x -C /tmp/opencode/proofs/baseline-tz
$ /tmp/opencode/perps-p0-venv/bin/python -m pytest -q tests/ml/test_baseline_labels.py
11 failed, 18 passed in 23.21s
```

After `uv pip install tzdata`, the same file is `29 passed in 20.94s` and the
full suite is clean. No repository file in `tests/ml/` or `ml/` was changed.

### Reproduce

```bash
# proofs (fresh archives; never recursive worktree copies)
git archive origin/main | tar -x -C /tmp/opencode/proofs/old-behavior
git archive 0a06b20d29c2daa254d8bfd86f474966d2e9005d | tar -x -C /tmp/opencode/proofs/mut-good-friday
# remove Good Friday rows, run tests/perps/test_market_calendar.py
# relax _SYMBOL_RE to "[:-]", run tests/perps/test_perp_universe.py
```

## 5. Deviations, flags and owner decisions

1. **`uv` was not on PATH.** Provisioned into `/tmp/opencode/uvtool` from the
   PyPI wheel (no repository change), then used for `uv venv` and
   `uv pip install`. This is the only acceptance deviation.
2. **`tzdata` added to the venv.** The uv standalone CPython's OS tz database
   lacks legacy aliases such as `US/Eastern`; CI's system Python normally has
   them. This is an environment-only fix, proven pre-existing (§4 P4). The
   repository requirements are unchanged.
3. **Live probe not run.** The request says the coordinator runs it live.
   `--dry-run` is the default and makes zero network calls; `--live` writes
   `docs/data/perps_history_probe.json` and `.md`. No probe output is committed.
4. **Offline SEC CIK map is sparse.** `tests/rag/fixtures/sec/company_tickers.json`
   maps only 10 tickers; 5 of the 78 perp companies are mapped. The report says
   this explicitly and supports `--cik-map <full snapshot>`. Do not treat the
   73 "unmapped" rows as an SEC conclusion.
5. **`BOT` group/description mismatch.** `config/tickers.yaml:1900` has
   `BOT  # "RoboStrategy, Inc. Common Stock"` inside `closed_end_fund_equity`;
   the report flags it as `fund` from the group. Owner decides whether to keep.
6. **No OI history.** Public Hyperliquid info API is current-only; the plan
   presents forward snapshots (recommended) and S3 backfill (owner approval).
7. **No signal publication.** P0 is scaffolding only; `gold_weekend_perp_features`
   and all P2+ jobs are planned, not implemented or scheduled.

## 6. Non-goals / untouched

- No changes to `requirements*.txt`, `.github/**`, `app.yaml`, `databricks.yml`,
  `resources/**`, `api/**`, `agent/**`, `execution/**`, `db/**`, `silver/**`,
  `gold/**` or `sql/**`.
- No ingestion job, table, schedule, model, signal or shared-table write.
- No network in tests; the hermetic guard is active for the whole suite.
- No pandas/DuckDB imports in the new modules or tests.
