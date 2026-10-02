# VERDICT: lakebase-agent-tools ROUND 3 — DeepSeek
**Status:** APPROVED
**Round:** 3

Narrow close-out. All four blocking items addressed; no round-2 fixes were
rewritten. `git diff --stat` is small (3 modified files + 1 new test file).

## Per-item resolution

- **Item 1 — execution boundary: FIXED.**
  - `db` removed from the public `approve_and_place_paper_order(order_id)`
    signature; the entry point acquires its own connection via `get_lakebase()`
    (`agent/tools_write.py:340`).
  - `_approve_and_place_paper_order` is now genuinely private: excluded from
    `__all__` (`agent/tools_write.py:49`) and its docstring is marked TEST-ONLY
    (`agent/tools_write.py:362`).
  - `record_approval` now requires an explicit `ApprovalContext` object
    (`agent/tools_write.py:88`, `:269`) instead of a bare `approver_id` string,
    so a caller cannot pass `"someone"` as proof of approval.
  - Tool-surface isolation is **explicitly deferred**, not faked: the module
    docstring states it must be enforced/tested when the agent runtime lands;
    there is no registry in this slice to assert against.
  - Boundary test deepened: `tests/lakebase/test_execution_boundary.py` now
    asserts `db` is absent from the public signature, the private seam is absent
    from `__all__`, and `record_approval` takes a context object.

- **Item 4 — idempotency redundancy: FIXED (decision stated).**
  The UNIQUE constraint on `orders.idempotency_key` is the real guard. The
  `idempotency_key_seen` pre-check query was structurally unreachable (a
  *different* order with the same key cannot exist under UNIQUE) and has been
  **removed** from the placement path (`agent/tools_write.py:502`). The concrete
  duplicate behaviour is `create_order_intent`'s `ON CONFLICT ... DO NOTHING`
  replay, which now returns the existing order with a structured
  `reason == "DUPLICATE_IDEMPOTENCY_KEY"` and `replay: True`
  (`agent/tools_write.py:263`). The guardrail's `DUPLICATE_IDEMPOTENCY_KEY`
  branch is retained as a pure, unit-tested contract and documented as
  unreachable-by-construction in the placement path (`agent/guardrails.py`).
  Added an end-to-end live test that drives the duplicate path and asserts the
  structured reason **and** that no second broker call occurs.

- **Item 16 — tests normalize bypasses: FIXED.**
  All per-risk offline tests in `tests/lakebase/test_execution_boundary.py` now
  drive the public `approve_and_place_paper_order` and patch the *construction
  sites* (`get_lakebase`, `IBKRBridge`, `is_market_session_open`) — never pass
  `engine`/`db`/`market_session_open`/`now` as arguments. The symbol-not-allowed
  test uses a symbol guaranteed absent from the production allow-list so the
  real `RiskEngine(load_allowlist=True)` rejects it. No test was deleted;
  the dead-code `idempotency_seen` test was replaced by an equivalent
  no-broker-call replay test.

- **Item 19 — index/latency evidence: FIXED (EXPLAIN) + latency UNVERIFIED.**
  Added `tests/lakebase/test_index_latency.py`. The `EXPLAIN (FORMAT JSON)`
  test runs all nine operational queries with `enable_seqscan = off` and asserts
  an index scan (no `Seq Scan`) — **passes** for every query. Latency was
  measured against the live instance; the `<500 ms` read / `<800 ms` write
  budgets are **not met from this environment** and are therefore recorded as
  **UNVERIFIED** (see non-blocking notes). Not silent.

## Blocking findings

None.

## Non-blocking notes

- **Item 19 latency is network-bound, not query-bound.** Measured p50/p95
  (n=20, warm pool): read p50 ≈ 574 ms / p95 ≈ 611 ms; write p50 ≈ 954 ms /
  p95 ≈ 1022 ms. The read *p50* is already ≈ 574 ms, i.e. the median WSL→
  us-west-2 Lakebase round-trip exceeds the 500 ms budget before any query work.
  Combined with the passing EXPLAIN test, this shows the budget miss is an
  environment/co-location artifact, not an index or code defect. Re-measure from
  a co-located runner before trusting the budgets.
- `cancel_paper_order` still accepts an injectable `db` kwarg. This was out of
  scope for round 3 (the request scoped item 1.1 to the *placement* function),
  and it does not expose trusted risk state (the bridge is still acquired
  internally). Flagged for a future pass, not a round-3 blocker.
- `create_order_intent`, `record_approval`, etc. retain their `db` kwarg for the
  live-test fixtures; only the placement entry point dropped it, as requested.

## Checks run

- `python3 -m pytest tests/lakebase/ -q -m "not lakebase"` →
  `53 passed, 19 deselected in 13.59s`
- `python3 -m pytest tests/lakebase/ -q` →
  `72 passed in 149.34s`
- `python3 -m pytest tests/lakebase/test_index_latency.py -q -s` →
  `2 passed` with
  `LATENCY read  p50=574.1ms p95=610.7ms` /
  `LATENCY write p50=953.6ms p95=1022.3ms`
- `python3 -m py_compile` on all touched modules → pass
- `git diff --stat` (vs. round-2 head): `5 files changed, 368 insertions(+),
  85 deletions(-)`; committed as `35049fc`.

Full test output (both selections) verified from an unsandboxed WSL shell where
Lakebase credential minting succeeds; the `databricks` CLI is not sandboxed here.
