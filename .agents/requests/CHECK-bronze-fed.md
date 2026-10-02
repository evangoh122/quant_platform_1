# CHECK-REQUEST (DeepSeek = checker): bronze-fed

You are the **checker**. Do not modify production code or tests; read and run.
Branch `slice/bronze-fed`, worktree `/home/jianj/code/qp1-b-fed`. Specs:
`.agents/requests/BUILD-bronze-fed.md` (incl. the coordinator amendment on availability by
`revision_class`) and `BUILD-bronze-fed-round2.md`. Code: `notebooks/refresh_bronze_fed.py`,
tests `tests/bronze/test_refresh_bronze_fed.py`.

Claude verified LIVE: `bronze_fed_series` 96,992 rows. `market_rate` 91,913 rows, 0 stamped at
ingest, 0 available on/before observation date, 0 duplicate (series_id, observation_date,
vintage_date) keys; DGS10 2025 availability always next NY business day 16:30 local (DST-aware);
2025-07-03 -> 2025-07-07 (Jul 4 skipped). `revised_macro` 5,079 rows all = ingest_ts.

Check independently:
1. Is the next-business-day computation correct for weekends, US federal holidays, and DST
   transitions? Is there any holiday the federal calendar includes that the bond market does not
   close for (or vice versa) that would make a rate available a day early?
2. Can a `market_rate` observation ever be available before its value is actually published?
3. Is the write append-only, with an anti-join so re-runs cannot duplicate? Revised values appended
   as new vintages, never updating old rows?
4. Do the tests call production functions, and would they fail if the availability rule regressed
   to `max(next_business_day, ingest_ts)`? Prove it with a scratch copy under /tmp (never edit the worktree).

Run `python3 -m pytest tests/bronze/test_refresh_bronze_fed.py -q`. Verdict APPROVED or
CHANGES_REQUESTED with file:line evidence between `===VERDICT START===` and `===VERDICT END===`;
write it to `.agents/deepseek/VERDICT-bronze-fed-check.md` and commit only that file.
