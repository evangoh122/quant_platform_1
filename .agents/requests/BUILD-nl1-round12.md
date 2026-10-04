# BUILD nl1 round 12 (builder: MiMo; checker: DeepSeek; reviewer: Codex)

IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Commit after each item with descriptive
messages. NEVER delete or weaken existing tests.
Codex review: .agents/codex/VERDICT-nl1-review.md (CHANGES_REQUESTED). Fix findings 1–5. Finding 6 (PUBLIC_NL_ANALYTICS_V1_PLAN.md
in the diff): KEEP the file — Claude's decision; it is the owner's plan and is referenced.

## 1 (High). Point-in-time safety of the proposed views (docs/NL1_PROPOSED_SERVING_VIEWS.md)
The as-of filter (:10) is applied AFTER view computation, while rolling metrics (:145, :157) use globally selected rows, and
relative performance (:288, :301) uses benchmark data without propagating its availability.
- Restructure the proposed DDL so every derived metric is computed only from rows with information_available_ts <= :as_of
  (as-of filter applied to the INPUT rows before any window), or document the views as parameterised table functions taking
  as_of. Pick one approach and apply it consistently to every view.
- Every output row's information_available_ts = GREATEST(availability of every input row that contributed), incl. benchmark rows.
- Tests: a contract/doc test that parses the DDL and asserts (a) each view's window/aggregate CTE reads from an as-of-filtered
  input, (b) relative performance output availability includes the benchmark's. Mutation proof: move the as-of filter after
  the window → test FAILS.

## 2 (High). Column name mismatch close vs close_price
Price registry entries (semantic_registry_v1.yaml:23, :45, …) select/output `close`; the views expose `close_price` (:47).
Make them consistent (prefer the view's column names as the source of truth). Fix the tests: test_source_schema.py must check
registry columns against the specific VIEW's output columns only (no union with underlying source columns), and implement the
empty SQL-column checker at :146 (parse the view DDL's SELECT list). Mutation proof: rename a registry column to a non-existent
one → test FAILS.

## 3 (High). Insufficient-data honesty for sparse metrics
iv_atm exists for 12 of 19,390 gold rows (snapshot-only). Add to the contract/registry:
- per-metric `coverage` metadata (e.g. implied_volatility: availability "snapshot_only", min_coverage_ratio) and for every
  operation a response field for `sample_count` / `coverage_ratio` and a status enum incl. `INSUFFICIENT_DATA`.
- Policy: aggregate/trend/compare/rank on a metric whose coverage over the requested window is below threshold must return
  INSUFFICIENT_DATA (not a number). Implement the decision logic at the policy/contract level with injectable coverage stats
  (no Spark), and tests: IV aggregate over 2025 → INSUFFICIENT_DATA; put_call_ratio aggregate over 2025 → allowed.
  The aggregate output schema must allow null value when status is INSUFFICIENT_DATA.

## 4 (Medium). Policy enforces entity count minima and entity kinds
policy.py:162 entity-type validation is a no-op; only max counts checked (:179). Enforce registry min/max counts and allowed
entity kinds per (metric, operation). Tests: one-entity price.compare (min 2) → rejected; sector-level implied_volatility trend
→ rejected; valid cases accepted. Mutation proof: make the type check a no-op again → test FAILS.

## 5 (Medium). Relative performance semantics
Registry allows SPY/QQQ/RSP benchmarks (:556) but the view hardcodes SPY and computes a one-day difference, contradicting the
documented cumulative-return definition. Make the view take the benchmark as a parameter/column (SPY, QQQ, RSP) and compute
cumulative return over the requested window (entity cumulative − benchmark cumulative), consistent with the registry text.
Test the definition in the doc/DDL contract test.

## Acceptance
python -m pytest tests/analytics_nl -q all pass; pyspark hidden (PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps);
python -m analytics_nl.export_schemas --check passes (regenerate schemas via the exporter if contracts change).
.agents/mimo/VERDICT-nl1-round12.md with counts + all mutation outputs. Commit everything.
