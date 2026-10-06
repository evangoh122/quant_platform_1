# BUILD-ui-A5 round 4 (Codex sol CHANGES_REQUESTED — `.agents/codex/VERDICT-ui-A5-r3.md`)
You are MiMo. Branch `feat/ui-enhancement`, worktree /home/jianj/code/qp1-ui (check `git branch --show-current` before committing). Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`
or a script in `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` via `wsl -d Ubuntu -- bash <path>`. No PowerShell wrappers, nothing in C:\temp, NEVER npm ci/install, LF endings,
never touch `.agents/dispatch.sh`, stage only files you change, commit.
Fix: clearing the SymbolPicker (`SymbolPicker.tsx:168-170` calls `onChange('')`) must never cause a request with an empty symbol. In MarketDashboard and OptionsAnalytics, skip the
`useApi` fetch while the symbol is empty and show a "Select a symbol" prompt (keep the last valid symbol in the URL or clear it — be consistent across both screens). Same for any
other screen that feeds the picker value to an API (check ResearchAgent and SecFilingExplorer too).
Tests (render the production screens; fetch mocked per api/schemas.py): clear the picker → no fetch call whose URL ends in `/api/market/` or contains `/api/market/%20`/empty segment;
the prompt is shown; picking a symbol again fetches it. Mutation: remove the empty-symbol guard → test FAILS (run in a /tmp `git archive` copy, record output).
Verdict `.agents/mimo/VERDICT-ui-A5-r4.md`.
