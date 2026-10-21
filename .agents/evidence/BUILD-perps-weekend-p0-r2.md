# BUILD-perps-weekend-p0-r2 — implementation evidence

- **Request:** `.agents/requests/BUILD-perps-weekend-p0-r2.md`
- **Branch:** `feat/perps-weekend-p0`
- **Base (required HEAD):** `be06fb1b6b84fe36fedffe35003ca9425e4e47e4`
- **Code commit:** `8b93ccbd5d81574335a7a85fe1fade127c3e25be`
  (`feat(perps): closed-market liquidity tiers, commodity perps, derivatives metadata, liquidity re-measure tool (P0 r2)`)
- **Head to validate:** the SHA in the `BUILD DONE` line (this evidence file is
  committed on top of the code commit).
- **Environment:** WSL Ubuntu, `uv 0.13.4`, acceptance venv
  `/tmp/opencode/perps-p0r2-venv` (CPython 3.12.13, pytest 9.1.1) created with
  `uv venv` + the CI-parity requirement files (no `ibapi`; `requirements-app.txt`
  and stripped `requirements-dev.txt` installed as `.github/workflows/ci.yml`
  does), plus `tzdata` for the standalone uv CPython. No pandas/DuckDB in the
  new code; tests make no network calls; no live Databricks.
- **Line endings:** all changed/new text files verified LF
  (`grep -qU $'\r'` clean; see §6).
- **Not pushed.** No merge, deployment or shared-table write.

---

## 1. Owner decisions implemented

| # | Decision | Where |
|---|---|---|
| 1 | Closed-market liquidity measurement, v4 config, tiers A–D, flags | `config/perp_universe.yaml`, `config/perp_universe.py`, `scripts/perps/measure_closed_liquidity.py` |
| 2 | Commodities section (8 perps + Massive ETF pairing, `etf_kind`) | `config/perp_universe.yaml` `commodities:`, `PerpCommodity`, `load_perp_universe().commodities` |
| 3 | Perps are derivatives; `instrument_type` mandatory; underlying labels | `INSTRUMENT_TYPE`, `_require_instrument_type`, `_require_underlying_type`; `BOT→fund`, `STRC→preferred`, `KSTR→etf` |
| 4 | Productise the reference measurement tool | `scripts/perps/measure_closed_liquidity.py` (stdlib only, `config/market_calendar.py`, `--dry-run` default, `--live`, proposal only) |
| 5 | Ontology + README updates | `ontology/business_terms.yaml`, `ontology/filters.yaml`, `README.md` |
| 6 | Plan + architecture reflect v4 | `docs/data/PERPS_WEEKEND_PLAN.md`, `docs/data/perps_architecture.html` |

### 1.1 v4 config

`config/perp_universe.yaml` is `.agents/requests/perp_universe.v4.yaml` plus the
three owner-required underlying labels. The complete diff against the owner
file is exactly the three rows and two explanatory comment lines:

```text
- STRC ... underlying_type: equity -> preferred
- BOT  ... underlying_type: equity -> fund
- KSTR ... underlying_type: equity -> etf
+ # Underlying classification from the round-1 ticker check ...
+ # All three stay in the universe ...
```

Counts from the production loader (`python -m config.perp_universe`, exit 0):

```text
perp universe v4: 78 companies, 8 commodities, 2 controls
controls: binance_usdm:BTCUSDT, binance_usdm:ETHUSDT
tickers: SNDK, MU, NVDA, ... KSTR, GLW, TWST, UMC
commodities: xyz:CL, xyz:BRENTOIL, xyz:SILVER, xyz:GOLD, xyz:NATGAS, xyz:COPPER, xyz:PLATINUM, xyz:PALLADIUM
```

Tier distribution of the 78 companies: A 13, B 17, C 19, D 29.

### 1.2 Derivative metadata (owner rule 2026-10-22)

- `config/perp_universe.py:61` `INSTRUMENT_TYPE = "perpetual_future"`.
- `_require_instrument_type` (`:412`) rejects a missing value and any other
  value with a message naming `perpetual_future`.
- `_require_underlying_type` enforces the documented allowlist
  (`equity/etf/fund/preferred/commodity/crypto`) **and** the section rule:
  company rows may not be `commodity`, commodity rows must be `commodity`,
  controls must be `crypto`.
- `instrument_defaults` requires `is_equity: false`, `is_derivative: true`,
  `contract: linear_perpetual`.
- Company/commodity tiers must agree with the measured `weekend_usd_per_h`
  (`tier_for_weekend_usd_per_h`, `:289`), and the stored `flags` must agree with
  the measurement (`derive_flags`, `:301`; `new` = first bar after window start,
  `sparse` = >25% zero-volume weekend hours). Both rules are enforced by the
  loader, so a stale tier/flag is a loud failure rather than a silent label.
- The plan/architecture documents now carry the required NOT NULL
  `instrument_type`, `underlying_type`, `underlying_symbol`, `venue`,
  `contract_symbol` columns for every planned Bronze/Silver/Gold perps table,
  the `perp_` feature prefix, the UC comment prefix and derivative tags.

### 1.3 Commodity perps

`PerpCommodity` (`config/perp_universe.py:205`), parsed at `:734`. A commodity
row is rejected when `etfs` is missing/empty, when `etf_kind` is not
`physical|futures`, when `underlying_type != commodity`, or when its provider
symbol duplicates another instrument. `load_perp_universe().commodities` is the
public accessor; `commodity_count` is 8.

### 1.4 Closed-market liquidity tool

`scripts/perps/measure_closed_liquidity.py` (stdlib only):

- `weekend_windows_for` (`:167`) builds every break from
  `config.market_calendar.weekend_window`, so Labor Day ends Tuesday 09:30 ET
  and Good Friday starts Thursday 16:00 ET; no holiday set is hard-coded.
- `measure_candles` (`:202`) measures `weekend_usd_per_h`,
  `closed_usd_per_h`, first bar and zero-volume share from 1h candles
  (`volume × close`); only bars **fully inside** `[start, end)` count.
- `build_proposal` (`:288`) emits proposed tiers/flags for the 78 companies and
  8 commodities plus thresholds/window. The JSON states
  `config/perp_universe.yaml is not modified`; the tool never writes the config.
- `--dry-run` is the default and prints the 86 planned 1h requests with zero
  network calls. `--live` is required for network; `--candles-dir` reads
  recorded fixtures for offline/tests; rate limit ≤2 req/s with retry/backoff.
- Recorded fixtures: `tests/fixtures/perps/liquidity_candles/NVDA.json`
  (Labor Day weekend, 4 zero-volume hours) and `KSTR.json` (new + 30.77%
  zero-volume weekend hours).

### 1.5 Ontology and README

- `ontology/business_terms.yaml`: added `perpetual_future`, `underlying`,
  `underlying_type`, `funding_rate`, `open_interest`, `mark_price`,
  `oracle_price`, `weekend_window`, `closed_market_liquidity`, `liquidity_tier`,
  `new_flag`, `sparse_flag`, `commodity_perp`, `etf_kind`. The ambiguous
  `underlying` alias was removed from `ticker` so the new term has a single
  owner (the existing no-duplicate/no-double-owner tests enforce this).
- `ontology/filters.yaml`: `weekend_window` rule referencing
  `config/market_calendar.py`, no table/SQL columns (rule-only filter).
- `README.md`: new "Weekend perps research (planned/in progress)" section and
  Honest-status row: derivative framing, `config/perp_universe.yaml` v4, 78 + 8
  + 2, data sources, 1m retention, and "nothing live".

### 1.6 Plan and architecture

`docs/data/PERPS_WEEKEND_PLAN.md` now documents v4: derivative framing, tiers
A–D and flags, 8 commodity perps with `etf_kind`, `instrument_type` /
`underlying_type` / `contract_symbol` columns through Bronze/Silver/Gold, the
`perp_` prefix + UC comments/tags, the ~3.5-day API `1m` retention → daily
forward capture, 15m/1h history, full Binance `1m` archives for controls, and
the OI-history gap/options. `docs/data/perps_architecture.html` was updated with
the same v4 labels (config counts, source retention, 1m capture, commodity/derivative
cards), keeping the planned/dashed style.

### 1.7 Probe covers commodities

`scripts/perps/probe_history.py` now plans Hyperliquid streams for the 8
commodity perps as well as the 78 companies; the dry-run plan is **270**
requests (86 × 3 Hyperliquid + 2 × 6 Binance) and renders a commodity table
with the ETF wrapper and `etf_kind`.

---

## 2. Tests

`tests/perps/` + `tests/test_ontology.py` — **131 passed, 33 skipped** (27.69s):

```text
$ pytest -q tests/perps tests/test_ontology.py
131 passed, 33 skipped in 27.69s
```

New/updated perps coverage:

| File | Focus |
|---|---|
| `tests/perps/test_perp_universe.py` (44) | real v4 load 78+8+2 (`:40`), BOT/STRC/KSTR labels (`:68`), commodity ETF pairing (`:78`), tier/flag rules, missing/other `instrument_type` (`:157`), unknown `underlying_type` (`:180`), duplicate ticker (`:201`), commodity without `etfs` (`:220`), tier/flag drift, ETF kind, controls, versions |
| `tests/perps/test_measure_closed_liquidity.py` (11) | tier thresholds (`:27`), Labor Day window + Tuesday open (`:36`), holiday bar classification, fixture metrics, new/sparse flags (`:85`), dry-run zero network, fixture mode writes proposal and leaves config byte-identical (`:128`), malformed payload, rate cap |
| `tests/perps/test_probe_parsing.py` (14) | updated 270-request plan, commodity probe section, existing fixture parsing |
| `tests/perps/test_check_universe.py` (5) | unchanged report-only behaviour, still passes |
| `tests/test_ontology.py` | unchanged suite now green with the new terms/filter (no duplicate term or alias owner) |

### 2.1 Full CI parity (standing rule)

Exact CI command
`pytest -q -m "not spark and not lakebase and not databricks"`, run normally
and with a pyspark-blocking stub first on `PYTHONPATH`
(`/tmp/opencode/perps-p0r2-stub/pyspark/__init__.py` raises
`ModuleNotFoundError("No module named 'pyspark'")`, outside the repo):

```text
plain: 3031 passed, 71 skipped, 24 deselected, 46 warnings in 433.16s  (exit 0)
stub:  3031 passed, 71 skipped, 24 deselected, 46 warnings in 369.44s  (exit 0)
```

pyspark is genuinely absent from the venv (`import pyspark` →
`ModuleNotFoundError`).

---

## 3. Acceptance commands

All run from `/home/jianj/code/wt-perps-p0` with the acceptance venv; every
command exited 0.

| Command | Result |
|---|---|
| `python -m config.perp_universe` | `v4: 78 companies, 8 commodities, 2 controls` |
| `python -m config.market_calendar --check` | `OK (rules match static calendar)` |
| `python scripts/perps/probe_history.py --dry-run` | 270 planned requests; OI note present; zero network |
| `python scripts/perps/measure_closed_liquidity.py --dry-run` | 86 planned 1h streams; "never modified" note; zero network |
| `python scripts/perps/measure_closed_liquidity.py --candles-dir tests/fixtures/perps/liquidity_candles --symbols NVDA,KSTR --out /tmp/opencode/p0r2-proposal.json` | `mode fixtures`, 78 company + 8 commodity rows; NVDA `A ['new']`, KSTR `D ['new','sparse']` |
| `python scripts/perps/check_universe.py` | report-only, exit 0, no entries removed |
| `pytest -q tests/perps tests/test_ontology.py` | 131 passed, 33 skipped |
| `grep -rn "import pandas\|import duckdb" config/perp_universe.py config/market_calendar.py scripts/perps tests/perps` | no matches (`grep` exit 1) |

The proposal is written to `/tmp/opencode/p0r2-proposal.json` in the acceptance
run (an explicit `--out`); the default path is
`docs/data/perp_liquidity_tier_proposal.json`, still a proposal only.

---

## 4. Old-behavior proof (base `be06fb1`)

A `git archive` copy of the base commit under `/tmp/opencode/p0r2-old` (not a
worktree copy):

```text
old version: 1
old companies: 78
old commodity_count: MISSING
old first company instrument_type: MISSING
AssertionError: old universe is not v4
old-behavior exit=1 (expected 1)
```

So the v4 loader/commodity/derivative behaviour does not exist on the old
behavior; the new acceptance assertions fail there.

## 5. Mutation proof

`git archive` of the code commit under `/tmp/opencode/p0r2-mut`, mutation
`if value != INSTRUMENT_TYPE:` → `if value not in {INSTRUMENT_TYPE, "equity"}:`
in `_require_instrument_type`:

```text
421:    if value not in {INSTRUMENT_TYPE, "equity"}:
mutation-test exit=1 (expected 1)
E       Failed: DID NOT RAISE PerpUniverseError
tests/perps/test_perp_universe.py:162: Failed
FAILED tests/perps/test_perp_universe.py::test_rejects_non_perpetual_instrument_type
```

Control on the unmutated code commit: `1 passed` (exit 0). A loader that
accepts `instrument_type=equity` is therefore killed by the test.

---

## 6. Line endings

`grep -qU $'\r'` was clean (LF) for: `config/perp_universe.yaml`,
`config/perp_universe.py`, `scripts/perps/measure_closed_liquidity.py`,
`scripts/perps/probe_history.py`, the three changed test files, both candle
fixtures, `ontology/business_terms.yaml`, `ontology/filters.yaml`, `README.md`,
`docs/data/PERPS_WEEKEND_PLAN.md`, `docs/data/perps_architecture.html`.

## 7. Worktree state / non-goals

- Branch `feat/perps-weekend-p0`; code commit `8b93ccb`; **not pushed**.
- No ingestion job was deployed or run; no Delta table was created or written;
  no Databricks/Lakebase/network call was made by tests or acceptance except
  package installation.
- No pandas or DuckDB imports in the new code; no live network in tests.
- Only the expected `.agents/run-perps-p0r2-*.sh` driver scripts and their logs
  are untracked; no other unexpected worktree change. A stray Windows `nul`
  file created by an inspection command was removed.
- `check_universe.py` remains report-only; all 78 company entries are retained
  as the owner decided, including BOT/STRC/KSTR.
- OI history, live ingestion, signals and table creation remain out of scope
  (P2+), as documented in the plan.
