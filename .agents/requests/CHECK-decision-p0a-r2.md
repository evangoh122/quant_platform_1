# DeepSeek check — Decision Dashboard Phase 0a round 2

Validate exact commit `eb1c931f5dffba8e3b5211d3569c2049f5883797` read-only (MiMo round 2; binding request `.agents/requests/BUILD-decision-p0a-r2.md`; your prior verdict `.agents/deepseek/VERDICT-decision-p0a.md` was CHANGES_REQUESTED on aacee9c for the unordered Spark read in db/delta_adapter.py market_features).
MiMo's evidence `.agents/mimo/VERDICT-decision-p0a-r2.md` is a self-report; reproduce independently. Do not edit, commit, push, deploy or access credentials. Run via `wsl.exe -d Ubuntu -- bash /home/jianj/code/qp1-decision-p0/.agents/run-decision-p0a-check.sh` only.

## Required review
1. HEAD, clean tracked tree (git status --porcelain --untracked-files=no), ancestry from origin/main, scope (no api/ routes change beyond Phase 0a, no new deps).
2. Re-verify the prior blocker B1 is resolved at db/delta_adapter.py market_features; judge MiMo's site audit table: changed (market_features, read_analytics_table, get_cot_positioning + _build_cot_query), left (read_table, market_features_intraday, read_analytics_cdc_state). Decide whether leaving market_features_intraday unordered is acceptable or a blocker (it is a time-series Spark limit whose warehouse variant also lacks ORDER BY, so Spark and warehouse are at least consistent but both nondeterministic). Also confirm the COT warehouse ORDER BY addition is correct, does not change column sets, and its ascending/descending semantics match consumers.
3. Tests call real production functions with a recording Spark stub; no copied logic. Re-run mutations M1-M5 from the original request plus M6 (remove orderBy in market_features) and M7 (reverse order direction on a changed site) in isolated `git archive` copies (never git in a cp -r copy); every mutation edits code not a docstring and must fail a relevant test. Check .agents/run-mutations.py no longer uses --noconftest and that M4 now fails via the semantic NULL assertion.
4. Check the api/trading_days.py docstring fix is accurate.
5. Missing/vacuous/surviving proof or production defect => CHANGES_REQUESTED with file:line.

Write `.agents/deepseek/VERDICT-decision-p0a-r2.md`; end with exactly:
`VALIDATION DONE | verdict: <APPROVED|CHANGES_REQUESTED|FAILED> | sha: <full SHA or SHA_NOT_VERIFIED> | evidence: .agents/deepseek/VERDICT-decision-p0a-r2.md`
