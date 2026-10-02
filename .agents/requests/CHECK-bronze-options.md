# CHECK-REQUEST (DeepSeek = checker): bronze-options

You are the **checker**: read and run, do not modify production code or tests. Branch
`slice/bronze-options`, worktree `/home/jianj/code/qp1-b-options`. Spec: `.agents/requests/BUILD-bronze-options*.md`, plan
`docs/BRONZE_REFRESH_PLAN.md`. Code: `notebooks/refresh_bronze_options.py`, tests
`tests/bronze/test_refresh_bronze_options.py`.

Claude ran it LIVE from WSL; the written row deltas match the dry run exactly, with zero
duplicate keys in the new period and only WRITE/OPTIMIZE in table history.

Check independently:
1. Append-only in every path (including first-time table creation); anti-join on the full natural key.
2. A file/date is marked SUCCESS only after its rows landed and verification passed.
3. Timestamps are not altered in bronze (bars stay stamped at their source start time).
4. Credentials read from scope `evangoh_capstone` and never printed or logged, including in exceptions.
5. Do the tests call production functions, and would they fail if the dedup/anti-join broke?
   Prove one with a mutated copy under /tmp (never edit the worktree).
6. Re-run safety: would running `--write` again append 0 rows?

Run `python3 -m pytest tests/bronze/test_refresh_bronze_options.py -q` (from WSL: `wsl -e bash -lc ...`).
Verdict APPROVED or CHANGES_REQUESTED with file:line evidence between `===VERDICT START===`
and `===VERDICT END===`; write it to `.agents/deepseek/VERDICT-bronze-options-check.md` and commit only that file.
