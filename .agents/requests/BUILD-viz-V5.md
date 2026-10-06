# BUILD-viz-V5 — Positioning (owner: "I don't see any sign of positioning")

You are MiMo. Branch `feat/ui-visuals`, worktree /home/jianj/code/qp1-viz (`git branch --show-current` before each commit). Reuse the V1 chart primitives in
`frontend/src/components/charts/`. Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-viz && <cmd>'` or a script in `/home/jianj/code/qp1-viz/.agentlogs/<name>.sh` via
`wsl -d Ubuntu -- bash <path>`. No PowerShell wrappers, nothing in C:\temp, NEVER npm ci/install, no new dependencies, LF endings, never touch `.agents/dispatch.sh`, stage only files you change, commit per item.

## Live facts (Claude, 2026-10-06)
- `gold_cot_features` (CFTC Commitments of Traders, weekly, PIT key `information_available_ts` = CFTC release): mapped_asset, report_date, lev_money_net, lev_money_net_chg_1w,
  lev_money_pctile_52w, lev_money_zscore_52w, asset_mgr_net, asset_mgr_pctile_52w, crowding_score, regime_label. `silver_cot_positions` (15,427 rows, 2022-01-04..2026-09-01):
  report_date, market_code, contract_name, mapped_asset (equity_index/rate/fx/other/crypto/commodity), open_interest, dealer_net, asset_mgr_net, lev_money_net, other_rpt_net,
  non_rpt_net, dealer_pct_oi, asset_mgr_pct_oi, lev_money_pct_oi, release_ts. NO API or UI reads either table today.
- `gold_options_features`: oi_concentration / net_delta_exposure / iv_* are non-null on only 12 rows (one quote snapshot); put_call_ratio is dense (20,318 rows, 39 symbols, 2024-09-04..2026-10-01).

## Items
1. **API** `GET /api/positioning/cot?asset_class=equity_index&weeks=156` (new `api/routes/positioning.py`, typed Pydantic schemas in api/schemas.py, `Envelope` + freshness like the
   other routes, `Depends(get_current_user)`, read via `read_delta`, parameterized SQL, `weeks` bounded 4..520, `asset_class` validated against the 6 values). Returns per-week rows
   from gold_cot_features for that mapped_asset, plus `contracts`: latest-week rows from silver_cot_positions (contract_name, open_interest, dealer/asset_mgr/lev_money net and pct_oi)
   filtered by `release_ts <= now()`. Use `information_available_ts`/`release_ts` as the as-of — never report_date alone.
2. **API** extend nothing for options; the UI uses the existing `/api/market/{symbol}` options items.
3. **Screen** `frontend/src/screens/Positioning.tsx` + nav entry:
   - Asset-class selector (the 6 values). Line chart: leveraged-money vs asset-manager net positions over time (two series, gaps at null), with a 52-week percentile band/second
     panel and the latest crowding_score + regime_label as stat tiles stamped with report_date AND release date.
   - Contract table/diverging bar chart for the latest week: net % of open interest by participant (dealer / asset manager / leveraged money), sorted by |lev_money_pct_oi|.
   - "Options positioning" card per selected symbol (SymbolPicker): put/call ratio trend (dense) + the single-snapshot OI concentration / net delta exposure shown as stats with
     their snapshot date and a note "snapshot only — no history". Never draw a line for them.
   - Caption: "CFTC data are weekly, released Fridays for the prior Tuesday; futures positioning by trader category, not single-stock holdings."
Tests:
- pytest `tests/api/test_positioning.py`: bad asset_class → 422; weeks out of range → 422; SQL is parameterized (no f-string interpolation of user input); rows with release_ts in
  the future are excluded (mutation: drop the release filter → fails); auth dependency present.
- Vitest (production screen, fetch mocks per the new schemas): two series drawn; a null week breaks the line; stat tiles show both dates; contracts sorted by |lev_money_pct_oi|;
  options card shows OI concentration as a stat and no OI line when only one row has it (mutation: chart it → fails); empty → EmptyState; error → ErrorState.
Run each mutation in a /tmp `git archive` copy; full `python -m pytest -q` + vitest + tsc + build. Verdict `.agents/mimo/VERDICT-viz-V5.md`.
