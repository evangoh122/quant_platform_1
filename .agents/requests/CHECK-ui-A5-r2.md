# CHECK round 2: UI A5 (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies (+ symlink frontend/node_modules; NEVER npm ci/install). Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r1 verdict: .agents/deepseek-fallback/VERDICT-ui-A5.md. Fixes eb69f8e (URL symbol lifted to parent), 2ae8ec9 (null close/volume dropped, not zero), 1b3dc77 (typed ticker submission in the SEC
fallback). Spec .agents/requests/BUILD-ui-A5-r2.md. Claude: vitest 162 passed, tsc clean; zero-fill of null closes → 1 failed.
1. Re-run your r1 findings' mutations: ignore ?symbol=; `?? 0` back; fallback rejects typed tickers.
2. Item 4 — there is no separate commit for it: re-run the three r1 survivors (unsorted chart rows; coverage indicator for an empty envelope; table data removed while the table renders). Any survivor
   is blocking.
3. Re-run the A5 named mutations from docs/ui_enhancement/BUILD-ui-A5.md and the SEC (#41) mutations; A1–A4 not regressed.
