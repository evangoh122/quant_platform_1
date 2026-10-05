===VERDICT START===
Status: CHANGES_REQUESTED

Findings:
1. `api/routes/agent_chat.py` / `agent/runtime.py`: (BLOCKING) Missing corrective retry and plain-prose final answer. The PR #37 description mentions "plain-prose final answer, one corrective retry" but neither is implemented in the runtime. The `parse_json_response` only handles JSON blocks wrapped in prose/markdown fences, but pure prose final answers fail parsing entirely, and there is no retry loop if validation or parsing fails.
2. `scripts/publish_baseline_signals.py:20`: (BLOCKING) PIT correctness / Target overlap. `nxt = df.groupby("symbol")["return_30m"].shift(-1)` is used as the label. If the snapshot frequency is higher than 30 minutes (e.g., 1m or 5m), the next snapshot's past-30m return heavily overlaps with the current snapshot's past-30m return, causing a massive lookahead data leak where the label includes past returns. Furthermore, across overnight gaps, `shift(-1)` grabs the next morning's return rather than the forward 30m return.
3. `scripts/publish_baseline_signals.py:27`: (BLOCKING) Test data leak in train/test split. `tr, te = lab[lab.prediction_ts <= cut], lab[lab.prediction_ts > cut]` includes the row at `cut` in the train set. However, because its label was generated via `shift(-1)`, the label is derived from the row at `cut + 1` (the next snapshot), which belongs to the test set.

All other safety properties (write authorization, idempotency, prompt-injection, unvalidated tool guardrails), CDC correctness, and Lakebase auth requirements check out.
===VERDICT END===
