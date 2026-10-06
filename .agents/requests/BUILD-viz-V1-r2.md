# BUILD-viz-V1 round 2 (luna CHANGES_REQUESTED — `.agents/deepseek-fallback/VERDICT-viz-V1.md`)
You are MiMo. Branch `feat/ui-visuals`, worktree /home/jianj/code/qp1-viz. Same shell rules as BUILD-viz-V1.md (WSL direct, no PowerShell/C:\temp, NEVER npm ci/install, stage only
your files, commit — do not leave work uncommitted).
Fix `frontend/src/screens/OptionsAnalytics.tsx:111-124`: put and call volume must be STACKED in one bar per feature_ts (call on put, or a shared `StackedBarSeries` primitive in
components/charts), with a null put or call drawn as a missing segment, not zero height pretending to be data. Test: for a row put=100, call=300 the call segment's y equals the top of the
put segment and the total bar height maps to 400 (mutation: side-by-side layout → fails). Run the full vitest/tsc/build. Verdict `.agents/mimo/VERDICT-viz-V1-r2.md`.
