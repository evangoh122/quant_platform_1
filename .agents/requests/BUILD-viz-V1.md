# BUILD-viz-V1 — chart primitives + three charts on existing APIs

You are MiMo. Branch `feat/ui-visuals`, worktree /home/jianj/code/qp1-viz (`git branch --show-current` before each commit; stay on it). Read docs/ui_enhancement/PLAN-V-visuals.md.
Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-viz/frontend && npx vitest --run && npx tsc --noEmit && npm run build'` directly, or a script in
`/home/jianj/code/qp1-viz/.agentlogs/<name>.sh` run via `wsl -d Ubuntu -- bash <path>`. No PowerShell wrappers, nothing in C:\temp. NEVER run npm ci/install, never add a dependency.
LF endings; never touch `.agents/dispatch.sh`; stage only files you change; commit per item.

1. **Shared primitives** `frontend/src/components/charts/`: linear/time/band scales, axes with ticks, `LineSeries` that BREAKS at null (gap, not zero), `BarSeries`, tooltip on hover AND
   keyboard focus, `ChartFrame` (title, caption, legend, `<details>` data-table fallback), dark-mode via existing tokens. Reuse in MarketDashboard's price chart if it is a clean drop-in;
   otherwise leave MarketDashboard alone.
2. **Options put/call timeline** in `screens/OptionsAnalytics.tsx` (data: `/api/market/{symbol}` → `options.items`, OptionsFeature in api/schemas.py): stacked put/call volume bars by
   feature_ts + put_call_ratio line + volume_anomaly_zscore line (separate axis or small-multiple). Use the shared SymbolPicker. Do NOT chart iv_* as a time series (populated for one
   snapshot only): show the latest IV values as a stat with its date.
3. **Signal conviction ranking** in `screens/SignalExplorer.tsx` (`/api/signals`, Signal schema): sorted horizontal bars of probability, coloured by direction, labelled
   "Baseline model probability" with model_version/horizon/prediction_ts in the caption — never "expected return".
4. **SEC coverage chart** in `screens/SecFilingExplorer.tsx` or PlatformOverview (`/api/sec/coverage`): top-N (default 25, toggle all) bars of n_chunks per ticker with n_filings in
   the tooltip/table; headline counts (tickers with chunks / total).

Tests (Vitest + RTL; render the PRODUCTION screens with fetch mocks matching api/schemas.py exactly; no copied logic):
- LineSeries renders 2 path segments for [1, null, 3] (mutation: coalesce null→0 → fails).
- Options: given 3 rows with IV only on the last → no IV line exists, IV stat shows that row's date; ratio line drawn; table fallback lists the rows (mutation: chart iv_atm series → fails).
- Signals: bars sorted by probability desc; text "Baseline model probability" present; "expected return" absent (mutation: unsorted → fails).
- Coverage: 30 tickers → 25 bars by default, 30 after toggle, ordered by n_chunks (mutation: slice before sort → fails).
- Every chart: empty data → EmptyState, not an empty axis; API error → ErrorState.
Run each mutation in a /tmp `git archive` copy (never cp -r the worktree) and record FAILED output. Verdict `.agents/mimo/VERDICT-viz-V1.md` with test counts, tsc, build.
