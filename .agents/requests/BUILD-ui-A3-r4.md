# BUILD-ui-A3 round 4 (Codex CHANGES_REQUESTED)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/codex/VERDICT-ui-A3.md`. LF endings, never touch `.agents/dispatch.sh`.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`; if quoting is hard,
write to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run `wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat, no
PowerShell wrappers, nothing in C:\temp. Stage only files you change (no `git add -A`). COMMIT; verdict `.agents/mimo/VERDICT-ui-A3-r4.md` with FAILED
output per mutation (mutate in a /tmp `git archive` copy).
1. ArchitectureEvidence.tsx:56 — remove the stale `baseline-logreg-v0-2026-10-05` / `hold-out AUC 0.47` figures. Known-limitations copy becomes:
   "Baseline signals only: a 1-trading-day logistic-regression baseline used to demonstrate the pipeline — no validated trading edge claimed."
   Update ArchitectureEvidence.test.tsx:67-68 to assert that text and assert the absence of /AUC/i and /baseline-logreg-v0/. Mutation: put the
   v0/AUC copy back → a test fails.
2. ArchitectureEvidence.tsx:115-116 — do not hide the diagram behind role="img". Render the technical diagram as an ordered list (<ol>) of the 13
   nodes in pipeline order (visually styled as the flow), with an accessible heading; tests assert getAllByRole('listitem') returns the nodes in the
   exact order (Massive/SEC/CFTC/FRED → Spark → Delta bronze/silver/gold → FastAPI → React → AI agent → Lakebase → analytics_outbox → Spark analytics →
   Delta analytics). Mutation: swap two nodes → a test fails; re-add role="img" on the container → an accessibility test fails.
