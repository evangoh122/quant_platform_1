# BUILD-ui-A5 round 6 (Codex sol CHANGES_REQUESTED — `.agents/codex/VERDICT-ui-A5-r5.md`)
You are MiMo. Branch `feat/ui-enhancement`, worktree /home/jianj/code/qp1-ui (`git branch --show-current` before committing). Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`
or a script in `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` via `wsl -d Ubuntu -- bash <path>`. No PowerShell wrappers, nothing in C:\temp, NEVER npm ci/install, LF endings,
never touch `.agents/dispatch.sh`, stage only your files, COMMIT (don't leave work uncommitted; no stray files).
1. `MarketDashboard.tsx:53-70`: if the range has no finite `close` values, render the chart EmptyState (no axes, no 0.0–1.0 labels). Volume bars: null volume = no bar. Test: rows with all-null
   close/volume → EmptyState text and no `svg` axis labels. Mutation: drop the guard → fails.
2. `SymbolPicker.tsx:52,79-87`: "Recent" must update after a selection without remount (keep recent in state, refresh after `pushRecentSymbol`). Test: select TSLA → a TSLA recent button
   appears in the same render tree. Mutation: read recent only at mount → fails.
Run mutations in a /tmp `git archive` copy and record FAILED output. Verdict `.agents/mimo/VERDICT-ui-A5-r6.md`.
