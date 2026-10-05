# BUILD-ui-A3 round 6 (checker CHANGES_REQUESTED — snapshot-label test is vacuous)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/deepseek-fallback/VERDICT-ui-A3-r5.md`. LF endings, never touch `.agents/dispatch.sh`.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard,
write to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat, no
PowerShell wrappers, nothing in C:\temp. Stage only files you change. COMMIT; verdict `.agents/mimo/VERDICT-ui-A3-r6.md` with the FAILED output (mutate in a /tmp copy).
PlatformOverview.test.tsx:82-90 climbs to the overview root, which always contains a snapshot label. Make the check local: for every text node matching the
numeric-claim regex, its NEAREST card/evidence container (e.g. closest('[data-evidence-card]') — add that attribute to the labelled cards) must exist and contain
"Verified snapshot: 2026-10-05"; a figure outside any evidence card fails the test. Mutation: add an unlabelled "287M+ records" to the hero at
PlatformOverview.tsx:98 → the test fails.
