# Codex gpt-5.6-luna check (DeepSeek fallback) — viz V1 r2 + V5 (saved by Claude)

===VERDICT START===
Status: CHANGES_REQUESTED

Findings:

- `frontend/src/screens/OptionsAnalytics.tsx:127-132`: `put_volume ?? 0` draws calls from baseline when put data is null without a visible “put missing” marker, making missing data indistinguishable from zero.
- `api/routes/positioning.py:75`: weekly COT query lacks `information_available_ts <= now`, allowing future releases.
- `api/routes/positioning.py:96-97`: contracts query does not restrict results to the latest report week.

Validation: frontend Vitest (197), TypeScript, and build passed. V1 archive mutation failed as expected. Backend pytest was attempted with `python3` (no `python` executable) but hung during the first test and was terminated. PIT-filter archive mutation proof detected the removed predicate.
===VERDICT END===
===VERDICT END===
