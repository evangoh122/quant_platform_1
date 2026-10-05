# BUILD-ui-A3 round 5 (Codex round-2 CHANGES_REQUESTED — one finding)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/codex/VERDICT-ui-A3-r2.md`. LF endings, never touch `.agents/dispatch.sh`.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard,
write to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat, no
PowerShell wrappers, nothing in C:\temp. Stage only files you change. COMMIT; verdict `.agents/mimo/VERDICT-ui-A3-r5.md`.
PlatformOverview.tsx:82 and :98 repeat snapshot figures (10,720 and 287M+) outside the labelled evidence cards. Every numeric claim must carry
`Verified snapshot: 2026-10-05` next to it — or remove the repeated figures from the hero/stepper copy (preferred: keep numbers only in the labelled cards;
note 10,720 SEC chunks is outdated — the corpus is now ~134k across 228 tickers, so do not repeat it outside the dated card). Test: every element whose
text matches /\d[\d,.]*\s*(M\+|records|chunks)/ on the Platform Overview is inside a container that also contains "Verified snapshot: 2026-10-05".
Mutation: add an unlabelled "287M+ records" to the hero → test fails.
