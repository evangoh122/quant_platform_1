===VERDICT START===
# VERDICT: post-submission — DeepSeek (gate before Codex review)

**Status:** APPROVED
**Round:** 1

Checker read-only. All mutations applied to disposable `git archive HEAD` copies
under `/tmp/qp1-check/`; no worktree file edited. The review worktree is
`review/post-submission`, ahead of `origin/main` by only the two `.agents/`
request commits, so the reviewed code == `origin/main`.

## Focus-area results (the five CHECK questions)

1. **Model can never execute a tool without `validate_next_action`** — VERIFIED.
   Single choke point: `agent/runtime.py:349` (`action = validate_next_action(raw_dict)`)
   is the only path to `agent/runtime.py:526` (`_tool_registry.execute(...)`).
   The prose-wrapping tolerance added in `56cd531`
   (`agent/model_client.py:260-301`, `parse_json_response`) only *returns* a dict
   — it never dispatches — so a prose-wrapped `{"action":"write",...}` still
   flows through `validate_next_action`. Mutation **MODEL-EXECUTES-DIRECTLY**
   (`action = raw_dict`) → `test_extra_json_fields` + `test_unknown_tool` fail
   (2 failed). The "corrective retry" named in the CHECK does **not** exist in
   the code (grep for `corrective|repropose|retry` finds only an unrelated HTTP
   retry in `etl/corporate_actions.py`), so the "retry skips validation" mutation
   is vacuous — the absence of a retry path is itself the absence of a bypass.
   See non-blocking note N1.

2. **REPLAY-INSERTS now FAILS** — VERIFIED. New offline regression
   `tests/agent/test_save_note_idempotency.py:65-74` drives the production
   `agent.tools_write.save_research_note` against a fake that honours
   `ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING`
   (`agent/tools_write.py:238`). Mutation (delete that clause) →
   `test_replay_with_same_key_does_not_insert_twice` FAILS with `assert 2 == 1`.
   This closes the r1 `llm-agent` blocker.

3. **CDC r1 blockers still fixed on main** — VERIFIED.
   * Per-table trigger functions (`db/migrations/004_analytics_outbox.sql:64-609`);
     no shared `NEW.watchlist_id`. `test_trigger_column_references_match_table_schemas`
     (`tests/rubric/test_outbox_sql.py:368`) enforces it.
   * Trigger events use `dedupe_key = NULL` (`:82` et al.) so successive UPDATEs
     don't collide on the `UNIQUE (dedupe_key)`; snapshot seeds use
     `snapshot:<table>:<pk>` (`:657+`). `test_trigger_events_use_null_dedupe_key`.
   * `DROP TRIGGER IF EXISTS … CREATE TRIGGER` (`:614-652`) → idempotent re-apply.
     `test_drop_trigger_if_exists`.
   * r1 blocker #4 (WATERMARK-SKIP / APPEND-DUPLICATE untested) closed:
     `test_claim_batch_selects_pending_by_null_delivered_at` and
     `test_merge_events_uses_merge_into` (`tests/rubric/test_outbox_sql.py:267,294`).
     Mutation (both applied together) → 2 failed.

4. **No secret/token in logs (SDK mint, model client)** — VERIFIED.
   `db/lakebase.py:60-64` (`_mint_token_via_sdk`) and `:98-101` (`mint_token_via_cli`)
   raise only `type(exc).__name__` + `request_id`, never raw error/CLI output; token
   is in-memory only (`LakebaseToken`, `:115-141`). `agent/model_client.py` logs
   `rid`/`endpoint`/latency/token counts (`:244-248`), transport errors as
   `type(e).__name__` (`:217-220`), and never `text`/`messages`/`raw` (`raw=None`,
   `:257`). Warehouse auth uses SDK default chain (`db/delta_adapter.py:180-187`),
   no embedded credentials.

5. **Signals script is PIT** — VERIFIED.
   `scripts/publish_baseline_signals.py:27` `label = sign(groupby(symbol).return_30m.shift(-1))`
   → labels derive from the **next (later)** snapshot only;
   `:30` `lab = df[df.label.notna()]` → training rows strictly labelled (last
   snapshot per symbol excluded); `:31-32` temporal 80/20 split on `prediction_ts`.
   `return_30m` is trailing (`gold/01_gold_ohlcv_features.sql:34`,
   `close/LAG(close,30)-1`), so the feature itself carries no look-ahead; the
   shifted trailing return is a legitimate later-snapshot label.

## Blocking findings

None.

## Non-blocking notes

- **N1** [CHECK premise drift] The request attributes "plain-prose final answer,
  one corrective retry" to Claude's live-integration fixes, but neither exists as
  a distinct path on main. What actually landed: prose/code-fence tolerance in
  `parse_json_response` (`agent/model_client.py:269-284`, `56cd531`) and a
  plain-prose `FinalAction.reply` return (`agent/runtime.py:365-376`). No
  corrective retry loop is present. This *strengthens* focus (1) (no retry path
  to bypass validation), but a future "corrective retry" added after this check
  must re-run the MODEL-EXECUTES-DIRECTLY mutation against it.
- **N2** The prose-wrapping tolerance (`parse_json_response`, `56cd531`) has no
  dedicated unit test (no `test_model_client.py`); only the safety property it
  preserves is covered indirectly via the bypass mutation. Recommend a small
  `parse_json_response` test (bare JSON, prose-wrapped, code-fenced, malformed).
- **N3** [pre-existing, not new] `db/delta_adapter.py` wraps warehouse reads in
  `try/except: return []`, so a genuine backend outage reads as "empty" rather
  than "unavailable" (carried from r1 CDC non-blocking note).

## Checks run

- `python3 -m pytest -q tests/agent tests/api tests/rubric --timeout 60` → **436 passed** (59.70s)
- REPLAY-INSERTS mutation (drop `ON CONFLICT` partial clause) → `tests/agent/test_save_note_idempotency.py` **1 failed**
- MODEL-EXECUTES-DIRECTLY mutation (`action = raw_dict`) → `TestMalformedResponse::test_extra_json_fields` + `test_unknown_tool` **2 failed**
- WATERMARK-SKIP + APPEND-DUPLICATE mutations → `tests/rubric/test_outbox_sql.py::test_claim_batch_selects_pending_by_null_delivered_at` + `test_merge_events_uses_merge_into` **2 failed**
===VERDICT END===
