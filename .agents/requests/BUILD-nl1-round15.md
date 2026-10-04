# BUILD nl1 round 15 (builder: MiMo) — one test

> CONTINUATION: your previous run stopped mid-task; partial edits are in the latest "wip(nl1): round 15 partial" commit. Run `git show HEAD`, finish, run both mutation proofs, write the verdict, commit. Do not start over.


IMPLEMENT NOW. Do not ask "Shall I proceed?". Stay on branch slice/nl-contracts. Descriptive commit. NEVER delete or weaken existing tests.
DeepSeek verdict: .agents/deepseek/VERDICT-nl1-round14.md — mutations a, c, d, e now fail; mutation (b) survives.

tests/analytics_nl/test_ddl.py:618-652 `test_output_availability_is_window_max` only counts availability tokens in the final GREATEST. Strengthen it:
for each token in the final GREATEST of each view (e.g. realized_vol_20d_info_ts, drawdown_info_ts — docs/NL1_PROPOSED_SERVING_VIEWS.md:197, :223;
entity_info_ts :393; bench_max_info_ts :419), resolve its definition in the CTE chain and assert it is `MAX(information_available_ts) OVER (...)`
with the SAME window frame as the metric it accompanies (or a GREATEST of such), or the base column only where no window/join is involved.
Mutation proof (in /tmp copy, paste output): replace realized_vol_20d_info_ts's `MAX(information_available_ts) OVER (... ROWS BETWEEN 19 PRECEDING
AND CURRENT ROW)` with the bare `information_available_ts` → the test FAILS. Repeat for drawdown_info_ts.
Acceptance: python3 -m pytest tests/analytics_nl -q all pass. .agents/mimo/VERDICT-nl1-round15.md with mutation outputs. Commit everything.
