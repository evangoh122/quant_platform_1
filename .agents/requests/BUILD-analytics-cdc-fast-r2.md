# BUILD-analytics-cdc FAST round 2 — IMPLEMENT NOW (DeepSeek CHANGES_REQUESTED; ~45 min time box)

You are MiMo. Branch `feat/cdc-analytics` (stay on it). Fix ALL blocking findings in `.agents/deepseek/VERDICT-analytics-cdc.md`.
Commit per item immediately, LF endings, never touch `.agents/dispatch.sh`, never weaken tests, paste each mutation's FAILED output in the verdict.
1. Trigger functions: ONE trigger function PER source table (e.g. `capture_outbox_watchlists()`, `capture_outbox_orders()`, …), each building
   `_pk` and the before/after payload ONLY from that table's real columns (check db/migrations/001–003 for exact column names). No shared
   function may reference a column that some table lacks. Keep explicit field lists, SECURITY DEFINER, fixed `search_path`, revoked PUBLIC execute.
2. Dedupe: trigger-generated events must NOT collide — dedupe_key is only for SNAPSHOT seeds (`snapshot:<table>:<pk>`); trigger rows get
   dedupe_key = NULL (UNIQUE allows multiple NULLs) or a per-event unique value (e.g. include txid_current() and a sequence). Successive UPDATEs
   of the same row must each produce their own outbox row.
3. Re-apply safety: `DROP TRIGGER IF EXISTS … ON …;` before each `CREATE TRIGGER`, `CREATE OR REPLACE FUNCTION`, `CREATE TABLE/INDEX IF NOT
   EXISTS`, snapshot seeds `ON CONFLICT DO NOTHING`. Fix the header comment.
4. Tests that bite: make WATERMARK-SKIP and the other surviving mutation fail (behavioural tests of the claim/merge functions with an
   out-of-order / gap fixture), and add a test that, for EVERY table with an outbox trigger, every `NEW.<col>`/`OLD.<col>` referenced in its
   trigger function exists in that table's CREATE TABLE in migrations 001–003 (parse the SQL) — mutation: reference NEW.watchlist_id in the
   orders function → FAIL.
Claude will apply 001–004 to a real throwaway Postgres (or Lakebase dev) and exercise insert/update/update/delete on every table.
Run: python3 -m pytest -q tests/rubric tests/api --timeout 60. Verdict: .agents/mimo/VERDICT-analytics-cdc-r2.md.
