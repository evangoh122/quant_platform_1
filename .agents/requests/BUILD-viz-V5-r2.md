# BUILD-viz V1/V5 round 2 (luna CHANGES_REQUESTED — `.agents/deepseek-fallback/VERDICT-viz-V1r2-V5.md`)
You are MiMo. Branch `feat/ui-visuals`, worktree /home/jianj/code/qp1-viz. Same shell rules as BUILD-viz-V5.md (WSL direct, no PowerShell/C:\temp, NEVER npm ci/install, stage only
your files, COMMIT). Python tests: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-viz && /tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/venv/bin/python -m pytest -q --timeout 120 tests/api/test_positioning.py'`.
1. `api/routes/positioning.py:75`: weekly COT query must filter `information_available_ts <= current_timestamp()` (or a bound now parameter). Test: a row released in the future is
   excluded from `weeks`. Mutation: drop the predicate → fails.
2. `api/routes/positioning.py:96-97`: contracts = only the latest report week whose release_ts <= now, for that asset class (e.g. `report_date = (SELECT MAX(report_date) ... WHERE
   release_ts <= now AND mapped_asset = :asset)`). Test: two weeks of contracts → only the latest released week returned; a later unreleased week is ignored. Mutation: drop the latest-week filter → fails.
3. `frontend/src/screens/OptionsAnalytics.tsx:127-132`: no `put_volume ?? 0`. When put or call is null, draw the known segment from the baseline with a visibly distinct "incomplete" style
   (hatched/outlined) and a "put missing"/"call missing" label in the tooltip and table; both null → no bar. Test asserts the incomplete marker and tooltip text. Mutation: `?? 0` → fails.
Run mutations in a /tmp `git archive` copy. Full vitest/tsc/build + positioning pytest. Verdict `.agents/mimo/VERDICT-viz-V5-r2.md`.
