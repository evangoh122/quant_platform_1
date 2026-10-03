# VERDICT: lakebase-agent-tools ROUND 2 — Claude (Architecture / Gate)
**Status:** CHANGES_REQUESTED (narrow — round 3 should be small)
**Round:** 2

## Correction to Codex's round-2 report

Codex reported the full test selection as `1 failed, 51 passed, 15 errors`, with
all live failures from Lakebase credential minting. **That is a sandbox
artifact, not a defect.** Codex's sandbox blocks the `databricks` CLI
subprocess, so minting fails inside it. Verified from an unsandboxed shell:

```
$ python3 -m pytest tests/lakebase/ -q -m "not lakebase"
51 passed, 16 deselected in 0.22s
$ python3 -m pytest tests/lakebase/ -q
67 passed in 76.96s
```

The instance is `AVAILABLE` and credential minting succeeds. **The full suite
passes, including all 16 live Lakebase tests.** Codex's item-by-item code
findings stand; only its test-result line was wrong.

## Round-2 assessment

Real progress. Offline coverage went 31 → 51 passing, and — the key round-1
defect — **the no-broker-call tests now run inside the offline selection**
rather than being excluded from the very command offered as proof.

Confirmed fixed, and these were the dangerous ones:
- `buying_power`, `idempotency_key_seen`, `is_paper` now read from real sources
  instead of constants.
- `SUBMITTED` removed from placement eligibility; submitted orders take an
  idempotent replay branch and do not re-call the broker.
- Failed submissions no longer return `ok: True`, and the audit row records
  `failed` rather than `success` — the `agent_actions` corruption I flagged is
  resolved, so `analytics_agent_activity` will not be poisoned.
- Allow-list fails closed.
- Broker call moved out of the open transaction.
- Credential errors sanitized.

17 FIXED, 3 PARTIAL, 1 NOT FIXED, 0 regressions.

## Remaining blocking items

- **[1] Execution boundary, PARTIAL.** The five dangerous parameters are gone
  from the public signature, but `db` is still caller-injectable,
  `_approve_and_place_paper_order` is directly importable, and `record_approval`
  takes a caller-supplied `approver_id` with only a docstring saying it "must"
  be authenticated. The boundary test only inspects five parameter names.
- **[4] Idempotency check, PARTIAL.** The query is real SQL but cannot become
  true under the unique-key schema — the unique constraint rejects the insert
  before the check can fire. Either the check or the constraint is redundant;
  decide which and make the behaviour explicit.
- **[16] Tests still normalize bypasses, PARTIAL.**
- **[19] Index/latency proof, NOT FIXED.** No `EXPLAIN`, no p95 measurement,
  and no honest statement that the budgets are unverified. This was explicitly
  requested in both rounds.

## Scoping judgement for round 3

The "tool registry / export boundary" part of item 1 **cannot be fully closed in
this slice** — there is no agent runtime or tool-registration layer in the repo
yet, so there is nothing to prove exclusion against. Round 3 should close what
is closable now (remove `db` from the public signature, make the seam genuinely
private, deepen the boundary test) and **explicitly defer** the
tool-surface-isolation proof to the agent-runtime slice, tracked rather than
quietly dropped. Demanding it now would invite a fake test.

## Gate

**BLOCKED** pending round 3. Round 3 is narrow: four items, no rewrites.
