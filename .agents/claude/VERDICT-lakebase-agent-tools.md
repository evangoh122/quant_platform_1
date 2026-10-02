# VERDICT: lakebase-agent-tools — Claude (Architecture / Gate)
**Status:** CHANGES_REQUESTED
**Round:** 1

I independently verified Codex's most severe findings at source rather than
accepting them. All spot-checks confirmed. One is worse than reported.

## Verified correct (credit where due)

- Live Lakebase schema is real and matches spec: 8 tables + `schema_migrations`,
  19 indexes, 5 CHECK constraints, and `REPLICA IDENTITY FULL` on exactly the
  seven behavioural tables with `users` correctly excluded. Confirmed by direct
  `information_schema` / `pg_class` query, not by reading code.
- The SQL-injection holes in the three retrieval tools are genuinely fixed —
  now Spark column expressions and `%s` parameters. No f-string SQL values remain.
- No secret or token committed.
- The six write tools do perform real Lakebase I/O. The UUID-fabricating stubs
  are gone.
- `CREATE PUBLICATION` really is disabled on this instance; that finding is
  accurate and correctly scoped out to the CDC slice.

## Blocking findings (mine, additional to Codex's 20)

- [agent/tools_write.py:325,338,342] **The audit trail is corrupted, not merely
  misleading.** `ok` is computed from the bridge response, used to derive
  `new_status`, then **discarded** — the function returns the literal
  `"ok": True`. Worse, `_log_action(..., "success")` is called on the same path.
  So a *failed* broker submission both reports success to the caller and writes
  a `status='success'` row into `agent_actions`. That table is the declared
  source for `analytics_agent_activity`, so this silently poisons the analytics
  slice downstream. Codex flagged the false return; the bad audit write
  compounds it and must be fixed together.

- **Three of the ten mandated risk checks are structurally dead**, wired to
  constants at [agent/tools_write.py:281,284,285]:
  `buying_power=_DEFAULT_BUYING_POWER` (100000.0), `idempotency_key_seen=False`,
  `is_paper=True`. The engine implementing them is well written, which makes
  this harder to spot and more dangerous: the checks appear covered.

- **Architectural:** the deterministic risk service is not a service. It is a
  pure function whose dependencies (`engine`, `human_approved`, `bridge`,
  `market_session_open`) are injected by the caller. The rubric requires a
  boundary the LLM *cannot* bypass. Dependency injection for testability is
  fine, but the production entry point must acquire trusted state itself and
  must not accept these as public parameters.

## Non-blocking notes

- `orders.symbol` added beyond the literal spec field list — I accept this.
  The justification is sound: the approve path needs the symbol for
  concentration/duplicate checks and it is unresolvable when `signal_id` is NULL.
- The ~25 pre-existing full-suite collection errors are genuine merge debt and
  correctly out of scope here. Tracked separately.

## Checks run

```
$ python3 -m pytest tests/lakebase/ -q -m "not lakebase"
31 passed, 15 deselected in 0.20s
```
```
$ grep -rnE 'f"' agent/ db/ | grep -iE 'select |insert |update |delete |where '
(no output — clean)
```
```
$ git grep -nIE 'sk-[a-zA-Z0-9]{20,}|eyJ[A-Za-z0-9_-]{20,}' HEAD
(no output — clean)
```
Live schema verified by direct Postgres introspection (tables, replica identity,
index count, check constraints) — see "Verified correct" above.

## Gate

**BLOCKED.** No PR. Round 2 required.
A builder self-verdict of APPROVED is not sufficient, and in this case was wrong.
