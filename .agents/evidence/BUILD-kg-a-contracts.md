# BUILD-kg-a-contracts — evidence (coder: DeepSeek `deepseek/deepseek-flash`, dsbuild stage)

Request: `.agents/requests/BUILD-kg-a-contracts.md`
Design of record: `.agents/requests/KG_DATA_MODEL_v2.md` -> `v3` -> `v4`; Sol R4 acceptance conditions are
`.agents/requests/SOL-kg-review-r4.md` (`ACCEPT_WITH_CHANGES`, `start_code: yes`).
Worktree: `/home/jianj/code/wt-kg-a`, branch `feat/kg-a-contracts` (branch created from `origin/main`
`0dc5b1c3e4598a6ea2c3b22f28cac7125da4b123`; stayed on it, nothing pushed).

## Commits (split because the change is ~5.7k lines; both reported)

| Commit | SHA | Contents | Lines |
|---|---|---|---|
| A | `82d88329f44aa168a4099588f77e9693aa4f9833` | `identity`, `temporal`, `names`, `filings` + their tests (commit message: `feat(kg): KG-A identity, temporal, name and filing contracts`) | +2,785 |
| B | `d0c2492a11d2f4237e52db9c3461e3efcdfc0b6d` | `facts`, `registry`, `publication` + their tests, full `__init__` (commit message: `feat(kg): KG-A facts, join registry, edge registry and publication contracts`) | +2,911 / -1 |

`d0c2492a11d2f4237e52db9c3461e3efcdfc0b6d` is the code SHA used for every acceptance and mutation run below.
The evidence commit on top of it adds only this file (`git diff --stat d0c2492..HEAD` = 1 file), so the reviewed
code tree is exactly the tree that was measured.
Commit B also deletes one trailing blank line from `tests/kg/test_filings_contracts.py` (whitespace hygiene found by
`git diff --check`; no functional change). Commit A was verified in isolation:
`git archive 82d8832 | tar -x -C /tmp/kg-a-commit-a` then `pytest tests/kg/test_{identity,temporal,names,filings}_contracts.py`
-> `6 passed` (log `.agentlogs/kg-a/run-kg-a-14.log`).

## Scope delivered (contracts only — no Spark job, no DDL, no table write, no reader change)

`sec_kg/contracts/` (new package, pure Python stdlib + `sec_kg.model`; no pandas/DuckDB/Spark/network):

- `identity.py` — v1 encoder reused **unchanged** by delegating to `sec_kg.model` helpers (Company, Filing,
  Section, Chunk, Metric; Concept keeps the v1 encoding), null-safe `kgid:v2` encoder for Security, Instrument,
  CryptoAsset, Period and Fact (`<presence><len:8hex><utf8>`); natural keys; provisional security id hashes the
  **smallest evidence id** (not a timestamp) so shuffled ingestion cannot change it; append-only alias maps with
  transitive resolution and cycle rejection; collision detection in both directions per (kind, version);
  `IdentityMigration` rows (`old_id, new_id, kind, identity_version, generation_id, reason`) with an
  end-to-end `apply_migration` that rewrites every reference (nodes, edges, evidence links, exports), derives Fact
  migrations from migrated Period ids, and is idempotent.
- `temporal.py` — insert-only `AttributeEvent` log; `system_from/system_to` **derived** from `recorded_at` +
  supersession (direct superseders, empty intervals allowed and never visible); dangling and cyclic supersession
  rejected; `public_as_of(ctx)` and `system_replay(ctx)` resolve through one `resolve(...)` that filters by
  knowledge time first and then resolves business time; public eligibility requires a **known** availability and
  deliberately does not require the row to be the current belief, so a future-public correction cannot erase an
  eligible predecessor; inclusive-date -> half-open helpers; single-attribute resolution guard.
- `facts.py` — `SeriesKey`/`AssertionKey`/`ObservationKey`; `entry_hash` over the canonical JSON of
  `value_raw, unit, start, end, instant, fy, fp, form, filed, frame, accn`; observations keep differing entries
  (`∅` dimensions documented as a constant); deterministic de-duplication that flags genuine payload collisions;
  `filter_observations` then `_precedence_selection` (latest public availability -> amended form -> newest
  system_from -> smallest entry_hash/evidence); `reconcile_series`; `ExtractedFact`/`LinkCandidate`/`link_extracted_fact`
  rejecting cross-issuer, metric, period, unit, dimension and value mismatches and returning `ambiguous` instead of
  guessing; explicit decimal tolerance (`decimals=0` exact, otherwise one unit of the last stated decimal).
- `registry.py` — typed `JoinContract` matrix (grain, namespace, business-time column, **stored** availability
  column, AS-OF predicate, cardinality, bridge, SQL evidence anchor) for `gold_ohlcv_features`,
  `gold_options_features`, `gold_model_features`, `gold_tradable_universe`, `silver_sec_sections`,
  `gold_sec_chunk_embeddings`, `silver_sec_xbrl_facts`, `bridge_security_symbol`, `perps_bars`; executable
  `check_grain`, `check_cardinality`, `is_available`, `as_of_predicate`; `SecuritySymbolBridge` with
  overlap validation and business-time (not query-time) resolution that ignores bridges not yet observed;
  `EdgeContract` registry for all 13 v1 edge types plus `AMENDS`, `HAS_SECURITY`, `LISTED_AS`, `UNDERLIES`,
  `INFERRED_PEER` (explicit endpoints/identity/evidence/scope, symmetric peers stored once, lower id first);
  `validate_edge`, `edge_identity_values`, canonical `serialize_edge` (sorted keys, decimals as strings, explicit
  nulls, every required field present).
- `publication.py` — immutable `Generation` manifest (status excluded from the content digest), injected
  `PointerExecutor` protocol, `publish()` state machine: bootstrap insert, exactly one CAS winner, unchanged
  pointer + `FAILED` run on a loss, retry of a current generation as a no-op success, manifest conflict on
  reused id with different content; deterministic `row_owner` (INSTANCE_OF/FOR_PERIOD owned by the source
  fact's company; Metric/Period/Concept/CryptoAsset global; INFERRED_PEER cross-company), `plan_subset`
  (predecessor minus member-owned rows plus rebuild; global rows retained; cross-company rows never rebuilt),
  `check_subset_allowed` rejecting stale/deleted/added member classification observations.
- `names.py` — submissions `formerNames` intervals with explicit inclusive -> half-open conversion, current name
  from the end of the last former name (or first observation), Company-Facts `entityName` kept as
  observation-only evidence, gaps never filled, overlaps resolved by rank then smaller evidence id.
- `filings.py` — accession de-duplication: shared value wins, disagreement takes the earliest `ingest_ts` with the
  smallest `record_key` breaking ties, absent metadata becomes `null` plus a `missing` quality issue, conflicts are
  reported, `period_of_report`/amendment target stay nullable-by-design, output fully order-independent.

## Required tests (exact Sol R4 names, one per acceptance item, all in `tests/kg/`)

| Test | File |
|---|---|
| `test_extracted_link_requires_unique_company_metric_period_unit_dimensions_value` | `tests/kg/test_facts_contracts.py:85` |
| `test_filter_before_reconcile_amendment_T1_T2` | `tests/kg/test_facts_contracts.py:169` |
| `test_observation_conflicts_survive_dedup_and_shuffle` | `tests/kg/test_facts_contracts.py:260` |
| `test_correction_split_replay_boundaries` | `tests/kg/test_temporal_contracts.py:93` |
| `test_public_view_supersession_without_future_leakage` | `tests/kg/test_temporal_contracts.py:236` |
| `test_publication_bootstrap_race_stale_predecessor_retry` | `tests/kg/test_publication_contracts.py:78` |
| `test_subset_equals_full_for_owned_rows_and_evidence` | `tests/kg/test_publication_contracts.py:220` |
| `test_security_identity_permutation_alias_cycle_and_ticker_reuse` | `tests/kg/test_identity_contracts.py:37` |
| `test_unchanged_v1_ids_and_complete_v2_reference_migration` | `tests/kg/test_identity_contracts.py:141` |
| `test_submissions_name_intervals_gaps_overlap_date_boundaries` | `tests/kg/test_names_contracts.py:37` |
| `test_filing_dedup_equal_ingest_missing_metadata_shuffle` | `tests/kg/test_filings_contracts.py:96` |
| `test_join_registry_business_time_availability_and_cardinality` | `tests/kg/test_registry_contracts.py:28` |
| `test_edge_registry_endpoints_identity_and_serialization` | `tests/kg/test_registry_contracts.py:252` |

13 test functions, exactly one function per required name (`grep -c "^def test_"` = 13). Tests call production
functions only; shuffle cases use `itertools.permutations` (no hypothesis); no network, no Spark, no pandas, no
DuckDB; the session hermetic guard is active.

## Acceptance (CI parity) on `d0c2492`

Both runs executed the exact CI command from `.github/workflows/ci.yml` on the committed tree.

| Run | Command | Result | Log |
|---|---|---|---|
| normal | `pytest -q -m "not spark and not lakebase and not databricks"` | **1 failed, 2955 passed, 64 skipped, 24 deselected** (263.97s) — the single failure is pre-existing, see below | `.agentlogs/kg-a/accept-normal-final.log` |
| pyspark blocked | same command with `PYTHONPATH=/tmp/kg-a-pyspark-stub` first, where `pyspark/__init__.py` raises `ModuleNotFoundError("No module named 'pyspark'")` (stub verified to block before the run) | **2946 passed, 74 skipped, 24 deselected, exit 0** (269.00s) | `.agentlogs/kg-a/accept-pyspark-blocked-final.log` |

Frozen existing suite: `pytest -q tests/rag/test_sec_knowledge_graph.py` -> `172 passed`.

Targeted new suite: `pytest -q tests/kg` -> `13 passed`.

### The one normal-mode failure is pre-existing

`tests/rag/test_zz_isolation.py::test_databricks_connect_not_polluted` fails because this developer machine has
`databricks-connect` installed, so an earlier rag test leaves `databricks.connect` in `sys.modules`. It reproduces
on a pristine `git archive origin/main` copy:

- pristine `origin/main`, same command: **1 failed, 2942 passed, 64 skipped, 24 deselected** (371.09s),
  same test (`/tmp/kg-a-baseline-full.log`). Branch total = 2956 vs baseline 2943, i.e. exactly the 13 added tests.
- with pyspark blocked (no `databricks-connect` import) the failure disappears on both trees; branch run is
  entirely green (2946 passed).
- `pytest -q tests/rag` alone passes on the pristine baseline (937 passed), so the failure needs the installed
  SDK plus whole-suite ordering, not this change.

### `uv venv` run (performed, then removed)

`~/.local/bin/uv` is not on `PATH`; invoked by absolute path. `uv venv .venv --python 3.12` plus
`uv pip install -r <ibapi-free requirements.txt> -r <ibapi-free, -r-free requirements-dev.txt>` (CI's sanitisation)
succeeded; the venv had `pandas`, `duckdb` and **no pyspark** (log
`.agentlogs/kg-a/kg-a-accept-uv-venv.log`). Results in that venv:

- `12 failed, 2938 passed, 70 skipped` (normal) and the same with the pyspark stub.
- 11 of the 12 are `tests/ml/test_baseline_labels.py`, all `zoneinfo.…ZoneInfoNotFoundError: 'No time zone found
  with key US/Eastern'`: the uv-managed CPython has no `tzdata` package while the system interpreter has the OS
  zoneinfo data. Reproduced on the pristine `origin/main` copy with the *same* venv (11 failed, 19 passed;
  `.agentlogs/kg-a/run-kg-a-12.log`) — independent of this change.
- The 12th is `tests/rag/test_sec_rag_ingest.py::TestNoPlaceholderUserAgent::test_no_example_com_or_your_email_in_production`,
  a repo-wide scan of every `.py`/`.yml` under the repo root. It flagged placeholder strings inside the 6.7 GB
  `.venv` tree that the throwaway environment itself had just created in the worktree; it passes on the same
  committed tree once that directory is gone (see the final normal run above).
- The venv was therefore deleted (`rm -rf /home/jianj/code/wt-kg-a/.venv`), leaving the worktree clean. The final
  acceptance runs use the system interpreter, which already carries the same packages CI installs with
  `uv pip install --system`; the pyspark-blocked run is the CI-parity proof.
- `venv`-only `tzdata` gap is an environment note for whoever re-runs this locally, not a repo defect; the build
  request does not ask for a requirements change and adding `tzdata` would be out of scope.

## Mutation proofs (one production mutation per required test)

Driver: `/tmp/kg-a-mutations/run_mutations.py` (scratch, outside the repo). Each mutation is applied to a fresh
`git archive HEAD` copy under `/tmp/kg-a-mutations/<name>` (never to the worktree), then the single named test runs.
Full output: `.agentlogs/kg-a/run-kg-a-16.log`; summary all 13 killed:

| # | Mutation (file) | Test that fails | Observed assertion |
|---|---|---|---|
| m01 | `facts.py`: extracted-fact pool no longer filtered by `company_id` | extracted-link test | `AssertionError: assert False` (ambiguous match) |
| m02 | `facts.py`: reconcile selected over *all* observations, then filtered | filter-before-reconcile test | `AssertionError: assert '120' == '100'` |
| m03 | `publication.py`: losing run keeps `pending` instead of `FAILED` (both branches) | bootstrap/race/retry test | `AssertionError: assert 'pending' == 'failed'` |
| m04 | `temporal.py`: `system_to` always `None` (correction never closes a belief) | correction replay boundaries | `AssertionError: assert None == 2022-03-01T00:00:00+00:00` |
| m05 | `identity.py`: provisional key uses evidence *iteration order* | security identity permutation/alias/cycle/reuse | `AssertionError: assert 3 == 1` (ids depend on shuffle) |
| m06 | `temporal.py`: public eligibility also requires `system_to is None` | public supersession without future leakage | `AssertionError` at `tests/kg/test_temporal_contracts.py:269` (predecessor erased) |
| m07 | `names.py`: inclusive end not advanced by one day | submissions name intervals/gaps/overlap/boundaries | `AssertionError: assert 2012-12-31 == 2013-01-01` |
| m08 | `facts.py`: `observation_key` ignores `entry_hash` | observation conflicts survive dedup+shuffle | `AssertionError` on observation-key tuple (entries collapsed) |
| m09 | `registry.py`: OHLCV availability re-derived as `feature_ts` | join registry business time/availability/cardinality | `AssertionError: assert 'feature_ts' == 'information_available_ts'` |
| m10 | `filings.py`: equal-`ingest_ts` tie-break reversed | filing dedup equal ingest/missing metadata/shuffle | `AssertionError: assert '10-Q' == '10-K/A'` |
| m11 | `registry.py`: symmetric edge order check removed | edge registry endpoints/identity/serialization | `Failed: DID NOT RAISE EdgeContractError` |
| m12 | `identity.py`: migration rewrites only `node_id/src_id/dst_id/entity_id` | unchanged v1 ids + complete v2 migration | `AssertionError: assert [('evidence', …)] == []` |
| m13 | `publication.py`: global-target edges owned as `global` | subset equals full for owned rows and evidence | `AssertionError: assert 'global' == 'company:co:A'` |

Driver verdict: `TOTAL 13 mutations, killed 13, not killed: none`, exit 0.

## Repository hygiene

- LF only: `grep -lU $'\r'` over `sec_kg/contracts` and `tests/kg` finds nothing; `git diff --check origin/main..HEAD`
  is clean.
- No `pandas`, `duckdb`, `pyspark` or `databricks` import in any new file (`grep -rnE "^(import|from) (pandas|duckdb|pyspark|databricks)"` -> none).
- Only new files: 8 files under `sec_kg/contracts/`, 8 under `tests/kg/`; no existing file modified
  (`git diff --stat origin/main..HEAD` = 16 files, +5,696/-1).
- No secrets created, read back or committed; no credential files touched; no network or Databricks calls.
- `git status` on the worktree is clean apart from gitignored scratch under `.agentlogs/` and `.agents/run-*.sh`.
- Nothing pushed; `main` untouched; no merge, deploy, table rebuild or model retrain.

## Deliberate decisions / notes for the reviewer

1. **Fact identity moved to v2** because a Fact id embeds its Period id (v4 §D, Sol S15); Company, Filing, Section,
   Chunk and Metric remain byte-identical v1 ids (locked with a frozen SHA-256 vector).
2. **`public_as_of` does not require the current belief** (v4 §F / Sol S3). Two different public corrections could in
   principle both be eligible; precedence picks the latest public availability and the older one becomes a reported
   conflict, which is what the leakage test pins down.
3. **`values_match`**: `decimals = 0` must match exactly (an integer-precision assertion cannot match `100.4`); for
   `decimals >= 1` a difference within one unit of the last stated decimal is accepted. Documented in the docstring.
4. **`Instrument` nodes** are treated as venue-scoped (kept by subset builds like global nodes) although v4 §G only
   names Metric/Period/Concept/CryptoAsset as global; `UNDERLIES` has no owning company.
5. **No DDL/SQL was added.** The registry's SQL anchors are read by the test to prove the availability column exists
   (`gold/01_gold_ohlcv_features.sql:102`, `gold/02_…:187`, `gold/05_…`, `gold/06_…:125`,
   `silver/05_silver_sec_sections.sql`); `gold_sec_chunk_embeddings` and `silver_sec_xbrl_facts` declare
   `via_join` availability because those tables do not store it.
6. `uv` is not on `PATH` in this environment; it was invoked as `/home/jianj/.local/bin/uv`. The system interpreter
   (Python 3.12.3, pytest 9.1.1) was used for the final acceptance runs, as documented above.

## Logs

All under `.agentlogs/kg-a/` (gitignored): `accept-normal-final.log`, `accept-pyspark-blocked-final.log`,
`run-kg-a-16.log` (mutations), `kg-a-accept-uv-venv.log`, `run-kg-a-14.log` (commit A in isolation),
`run-kg-a-12.log` (fresh-venv baseline comparison), `run-kg-a-9.log`/`/tmp/kg-a-baseline-full.log` (baseline).
