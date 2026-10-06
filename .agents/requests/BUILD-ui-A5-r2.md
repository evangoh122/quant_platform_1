# BUILD-ui-A5 round 2 (checker CHANGES_REQUESTED)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/deepseek-fallback/VERDICT-ui-A5.md` and docs/ui_enhancement/BUILD-ui-A5.md. LF endings, never touch `.agents/dispatch.sh`,
NEVER run npm ci/install. Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard, use
`/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` + `wsl -d Ubuntu -- bash <path>`. No PowerShell, nothing in C:\temp. Stage only files you change. COMMIT per item; verdict
`.agents/mimo/VERDICT-ui-A5-r2.md` with FAILED output per mutation (/tmp `git archive` copy). Tests may only render production components with mocks matching the real backend contracts.
1. SymbolPicker.tsx:64-67 — `?symbol=` must initialise the selection and drive the screen/API (lift it to the parent's state on mount; the controlled value must not overwrite it). Test: render with
   `?symbol=AMD` → the screen requests AMD. Mutation: ignore the URL param → fails.
2. MarketDashboard.tsx:61,80,133 — never convert null close/volume to 0: drop or gap null points (and show "n missing points" if any). Test: a series with nulls → no zero bars/points rendered for
   them. Mutation: `?? 0` back → fails.
3. SecFilingExplorer.tsx:136-139 + SymbolPicker.tsx:143-160 — in the coverage-failure fallback, typed tickers that pass the ticker format can be submitted (the server decides coverage);
   otherwise remove the "manual entry supported" copy. Test the chosen behaviour.
4. Kill the three surviving mutations: unsorted chart rows (test sorting explicitly), coverage shown for an empty envelope (empty coverage → no coverage indicator), table data removed while the
   table still renders (assert row contents, not just the table element).
