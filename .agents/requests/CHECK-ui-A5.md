# CHECK: UI slice A5 — SymbolPicker + market chart (+ post-merge regression fix) (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies (+ symlink frontend/node_modules; NEVER npm ci/install). Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Binding spec: docs/ui_enhancement/BUILD-ui-A5.md + .agents/requests/BUILD-ui-A5.md (item 0: the navigation test that broke after merging main — PR #41's SecFilingExplorer). Commit 6b30a27.
MiMo's verdict is a self-report. Claude: vitest 156 passed, tsc clean, build OK; spot check `inList = true` (SymbolPicker.tsx:125) → 1 failed.
1. Run every named mutation in docs/ui_enhancement/BUILD-ui-A5.md; list any survivor (blocking).
2. Item 0: the fix mocks /api/sec/coverage with the real shape {data, count, status} and does NOT weaken the navigation test.
3. SEC Research keeps #41's behaviour (coverage-backed selector, honest no_coverage / retrieval_unavailable states, stale-request guard) — re-run #41's key mutations against this branch.
4. Mocks match real backend contracts (api/routes/market.py, api/routes/sec.py, api/schemas.py); chart shows no fabricated or live-looking data; 360px; accessibility; A1–A4 not regressed.
