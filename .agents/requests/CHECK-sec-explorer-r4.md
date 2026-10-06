# CHECK: SEC Filing Explorer round 4 — Codex findings (checker)

Read-only; mutations only in `git archive HEAD | tar -x -C /tmp/<dir>` copies (+ symlink frontend/node_modules). Never run git inside a copy.
Findings: .agents/codex/VERDICT-sec-explorer.md (retrieval_unavailable rendered as a row; stale out-of-order responses). Fix 7e420c7
(spec .agents/requests/BUILD-sec-explorer-r4.md). Claude: frontend 21 passed, tsc clean.
1. Every error shape agent/tools_retrieval.py can return is handled (list them with file:line); unknown `{error}` never renders as a row.
2. Mutations, each must fail: drop the retrieval_unavailable branch; treat unknown errors as rows; remove the stale-response guard.
3. Re-run all earlier SEC explorer mutations (initial state, no-coverage, tool order, n_chunks filter, list cap, fallback).
