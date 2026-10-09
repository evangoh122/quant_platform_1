# DeepSeek check — Decision Dashboard Phase 0a (data correctness)

Validate exact commit `aacee9c6fd72ab8f0667be8854790f6da6e302d3` read-only (MiMo build; binding request `.agents/requests/BUILD-decision-p0a-data-correctness.md`). MiMo's verdict is a self-report; reproduce independently. Do not edit, commit, push, deploy or access credentials.

## Required review
1. Verify HEAD, clean tracked tree, ancestry from origin/main, scope = the 4 fixes + tests + evidence (no unrelated changes, no new dependencies).
2. Read the BUILD request completely; inspect every changed production and test file.
3. Run `.agents/run-decision-p0a-check.sh` ONLY via `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-decision-p0/.agents/run-decision-p0a-check.sh` (no inline bash -c, PowerShell, UNC, Windows node). One boundary failure => FAILED.
4. Verify each fix is correct in production code: (1) Spark orderBy(feature_ts DESC) before limit in agent/tools_retrieval.py, and check the market-features Spark read for the same defect; (2) api/trading_days.py start_for_trading_days weekday logic + api/routes/market.py uses it + freshness detail carries calendar_limited; (3) Position.realized_pnl/unrealized_pnl/market_price Optional, null preserved in API JSON, frontend renders em dash, excludes null from totals with an unpriced note, no NaN/$0.00; (4) gold/02_gold_options_features.sql z-score is NULL unless COUNT(total_volume) OVER w >= 20, column names unchanged.
5. Tests must call production code, never copy production logic (known MiMo failure mode). Check each test for vacuity. In isolated `git archive` copies (never git in a cp -r copy) re-run mutations M1-M5 from the request: each must fail a relevant test for the intended reason. Also inspect `.agents/run-mutations.py` for honesty.
6. Flag any weakness: e.g. tests that mock so heavily nothing real runs; trading-day helper edge cases (start on weekend, n=0/1, large n); frontend total excluding null correctly.
7. Missing/vacuous/surviving proof or production defect => CHANGES_REQUESTED with file:line.

Write `.agents/deepseek/VERDICT-decision-p0a.md`; end with exactly:
`VALIDATION DONE | verdict: <APPROVED|CHANGES_REQUESTED|FAILED> | sha: <full SHA or SHA_NOT_VERIFIED> | evidence: .agents/deepseek/VERDICT-decision-p0a.md`
