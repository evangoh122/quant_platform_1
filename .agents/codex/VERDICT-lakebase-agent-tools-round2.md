# VERDICT: lakebase-agent-tools ROUND 2 — Codex
**Status:** CHANGES_REQUESTED
**Round: 2**

The patch fixes most implementation defects, but the execution boundary remains only partially secured, the idempotency check is structurally unreachable, and the required latency/index evidence is still absent.

## Item-by-item validation

1. **PARTIAL — execution boundary non-bypassable**

   The public placement signature no longer accepts `engine`, `human_approved`, `approved_by`, `bridge`, or `market_session_open` ([agent/tools_write.py:287](/home/jianj/code/quant_platform_1/agent/tools_write.py:287)). However:

   - It still accepts caller-provided `db`, allowing a caller with Python-level access to supply fabricated orders, approvals, accounts, and buying power.
   - The injectable implementation remains directly importable as `_approve_and_place_paper_order` ([agent/tools_write.py:309](/home/jianj/code/quant_platform_1/agent/tools_write.py:309)).
   - No tool registry or export boundary proves the agent-facing surface cannot call that function.
   - `record_approval` accepts caller-provided `approver_id` and merely documents that it “must” be authenticated; no authenticated request context enforces this ([agent/tools_write.py:218](/home/jianj/code/quant_platform_1/agent/tools_write.py:218), [agent/tools_write.py:256](/home/jianj/code/quant_platform_1/agent/tools_write.py:256)).
   - The boundary test only inspects five parameter names and does not reject `db` or prove tool-surface isolation ([tests/lakebase/test_execution_boundary.py:255](/home/jianj/code/quant_platform_1/tests/lakebase/test_execution_boundary.py:255)).

2. **FIXED — `SUBMITTED` placement eligibility**

   `_PLACEABLE_ORDER_STATUSES` contains only `PENDING_APPROVAL` and `APPROVED` ([agent/tools_write.py:34](/home/jianj/code/quant_platform_1/agent/tools_write.py:34)). `SUBMITTED` remains in `_OPEN_ORDER_STATUSES` only for conflict detection ([agent/tools_write.py:39](/home/jianj/code/quant_platform_1/agent/tools_write.py:39)). Submitted orders take the idempotent replay branch and do not call the broker ([agent/tools_write.py:347](/home/jianj/code/quant_platform_1/agent/tools_write.py:347)).

3. **FIXED — buying power source**

   Buying power is read from the `accounts` table and missing accounts fail closed ([agent/tools_write.py:395](/home/jianj/code/quant_platform_1/agent/tools_write.py:395), [agent/tools_write.py:418](/home/jianj/code/quant_platform_1/agent/tools_write.py:418)). The accounts table is introduced by [db/migrations/002_approvals_accounts.sql:30](/home/jianj/code/quant_platform_1/db/migrations/002_approvals_accounts.sql:30).

4. **PARTIAL — idempotency-key source**

   The hardcoded `False` was replaced with a database query ([agent/tools_write.py:443](/home/jianj/code/quant_platform_1/agent/tools_write.py:443)). But it searches for a *different* order with the same key. Because `orders.idempotency_key` is unique, that state cannot normally exist, making `DUPLICATE_IDEMPOTENCY_KEY` structurally unreachable in the real database. The offline test fabricates an impossible result through `state["idempotency_seen"]` ([tests/lakebase/test_execution_boundary.py:91](/home/jianj/code/quant_platform_1/tests/lakebase/test_execution_boundary.py:91)).

5. **FIXED — paper-mode source**

   `is_paper` is derived from the stored order broker ([agent/tools_write.py:471](/home/jianj/code/quant_platform_1/agent/tools_write.py:471)) and passed into the risk context ([agent/tools_write.py:487](/home/jianj/code/quant_platform_1/agent/tools_write.py:487)).

6. **FIXED — allow-list fails closed**

   Allow-list loading now propagates import/configuration errors instead of returning `None` ([agent/guardrails.py:112](/home/jianj/code/quant_platform_1/agent/guardrails.py:112)). The fail-closed behavior has an offline test ([tests/lakebase/test_guardrails.py:174](/home/jianj/code/quant_platform_1/tests/lakebase/test_guardrails.py:174)).

7. **FIXED — unresolvable signal**

   A supplied but unresolved `signal_id` produces `SIGNAL_NOT_FOUND` and blocks placement ([agent/tools_write.py:456](/home/jianj/code/quant_platform_1/agent/tools_write.py:456), [agent/tools_write.py:493](/home/jianj/code/quant_platform_1/agent/tools_write.py:493)). A no-broker-call test covers it ([tests/lakebase/test_execution_boundary.py:230](/home/jianj/code/quant_platform_1/tests/lakebase/test_execution_boundary.py:230)).

8. **FIXED — conflicting opposite-side orders**

   Any open order for the same symbol now conflicts, regardless of side ([agent/guardrails.py:247](/home/jianj/code/quant_platform_1/agent/guardrails.py:247)). Opposite-side behavior is tested at [tests/lakebase/test_guardrails.py:106](/home/jianj/code/quant_platform_1/tests/lakebase/test_guardrails.py:106).

9. **FIXED — SELL concentration**

   SELL notional now reduces signed exposure, with the resulting absolute exposure checked against the cap ([agent/guardrails.py:222](/home/jianj/code/quant_platform_1/agent/guardrails.py:222)). Risk-reducing and overshooting SELL cases are tested at [tests/lakebase/test_guardrails.py:115](/home/jianj/code/quant_platform_1/tests/lakebase/test_guardrails.py:115).

10. **FIXED — broker call inside transaction**

    Submission intent is committed during phase 1 ([agent/tools_write.py:517](/home/jianj/code/quant_platform_1/agent/tools_write.py:517)); the broker call occurs after leaving that transaction ([agent/tools_write.py:527](/home/jianj/code/quant_platform_1/agent/tools_write.py:527)); the result is written in a new transaction ([agent/tools_write.py:537](/home/jianj/code/quant_platform_1/agent/tools_write.py:537)).

11. **FIXED — failed submission returning `ok: True`**

    `ok` now reflects the broker response, determines `FAILED` versus `SUBMITTED`, and is returned directly ([agent/tools_write.py:533](/home/jianj/code/quant_platform_1/agent/tools_write.py:533), [agent/tools_write.py:555](/home/jianj/code/quant_platform_1/agent/tools_write.py:555)).

12. **FIXED — fabricated cancellation success**

    Submitted orders require a broker identifier; otherwise cancellation is rejected ([agent/tools_write.py:605](/home/jianj/code/quant_platform_1/agent/tools_write.py:605)). Broker responses are evaluated, and rejection returns `ok: False` with `FAILED` ([agent/tools_write.py:619](/home/jianj/code/quant_platform_1/agent/tools_write.py:619)). Only never-submitted intents are cancelled locally.

13. **FIXED — unaudited early returns**

    Approval `NOT_FOUND`, replay, invalid state, missing approval/account, and risk rejection paths now log actions ([agent/tools_write.py:334](/home/jianj/code/quant_platform_1/agent/tools_write.py:334), [agent/tools_write.py:347](/home/jianj/code/quant_platform_1/agent/tools_write.py:347), [agent/tools_write.py:360](/home/jianj/code/quant_platform_1/agent/tools_write.py:360)). Cancellation `NOT_FOUND`, terminal, and invalid-state exits also log actions ([agent/tools_write.py:584](/home/jianj/code/quant_platform_1/agent/tools_write.py:584), [agent/tools_write.py:593](/home/jianj/code/quant_platform_1/agent/tools_write.py:593), [agent/tools_write.py:607](/home/jianj/code/quant_platform_1/agent/tools_write.py:607)).

14. **FIXED — risk tests previously exercised only pure engine**

    The new offline tests call the actual placement implementation and assert `bridge.submit_order.assert_not_called()` per check ([tests/lakebase/test_execution_boundary.py:114](/home/jianj/code/quant_platform_1/tests/lakebase/test_execution_boundary.py:114), [tests/lakebase/test_execution_boundary.py:137](/home/jianj/code/quant_platform_1/tests/lakebase/test_execution_boundary.py:137)).

15. **FIXED — only one aggregated no-call test, excluded offline**

    Individual no-call tests now cover symbol, paper mode, quantity, notional, maximum notional, concentration, buying power, conflicting orders, market closure, stale signal, and duplicate idempotency ([tests/lakebase/test_execution_boundary.py:138](/home/jianj/code/quant_platform_1/tests/lakebase/test_execution_boundary.py:138)). They are unmarked and ran in the offline selection.

16. **PARTIAL — tests normalize bypasses**

    Live tests exercise the public function and patch dependency construction rather than passing `engine`, `bridge`, or session state directly ([tests/lakebase/test_tools_write.py:44](/home/jianj/code/quant_platform_1/tests/lakebase/test_tools_write.py:44)). However, all per-risk offline tests call the directly importable private seam and inject `engine`, `bridge`, `market_session_open`, `db`, and `now` ([tests/lakebase/test_execution_boundary.py:114](/home/jianj/code/quant_platform_1/tests/lakebase/test_execution_boundary.py:114)). No test proves that this seam is absent from the actual agent tool registry.

17. **FIXED — migration-from-empty test**

    A scratch schema is created, migrations are applied, and the resulting tables are verified ([tests/lakebase/test_migrations.py:36](/home/jianj/code/quant_platform_1/tests/lakebase/test_migrations.py:36)). It could not complete in this environment because credential minting failed, but its construction now tests an initially empty schema.

18. **FIXED — cancellation round-trip coverage**

    The success test verifies both broker invocation and persisted `CANCELLED` state ([tests/lakebase/test_tools_write.py:166](/home/jianj/code/quant_platform_1/tests/lakebase/test_tools_write.py:166)). A separate test verifies broker rejection, `ok: False`, and persisted `FAILED` state ([tests/lakebase/test_tools_write.py:182](/home/jianj/code/quant_platform_1/tests/lakebase/test_tools_write.py:182)).

19. **NOT FIXED — index and latency proof**

    There are still no `EXPLAIN` tests, query-plan assertions, measured p95 read/write timings, or an explicit statement that the budgets remain unverified. Searching `tests/lakebase`, `agent`, and `db` found no `EXPLAIN`, percentile, or p95 evidence.

20. **FIXED — credential error sanitization**

    Credential-mint failures now expose only the exit code and generated request ID; raw stdout/stderr is withheld ([db/lakebase.py:64](/home/jianj/code/quant_platform_1/db/lakebase.py:64)).

21. **FIXED — failed submission corrupting audit status**

    The outcome audit uses `"success" if ok else "failed"` ([agent/tools_write.py:549](/home/jianj/code/quant_platform_1/agent/tools_write.py:549)), and the returned `ok` uses the same result ([agent/tools_write.py:555](/home/jianj/code/quant_platform_1/agent/tools_write.py:555)). Failed broker responses no longer write a success audit row.

## Test results

```text
python3 -m pytest tests/lakebase/ -q -m 'not lakebase'
51 passed, 16 deselected in 0.21s
```

The no-broker-call tests are included in this offline selection.

```text
python3 -m pytest tests/lakebase/ -q
1 failed, 51 passed, 15 errors in 2.09s
```

The full selection did **not** pass. All live failures/errors originated from Lakebase credential minting failing through the Databricks CLI:

```text
RuntimeError: Lakebase credential mint failed (exit code 1, request_id=...). Raw CLI output withheld.
```

## Overall

**CHANGES_REQUESTED**

Counts:

- **FIXED:** 17
- **PARTIAL:** 3
- **NOT FIXED:** 1
- **REGRESSED:** 0

The principal remaining blocker is the unproven execution boundary: the public function still accepts an injectable database, the approval writer trusts a caller-supplied identity, and the fully injectable seam is directly importable with no tool-registration proof excluding it. The idempotency query is also real SQL but cannot normally become true under the unique-key schema. Finally, the mandated index/p95 evidence remains entirely absent.

