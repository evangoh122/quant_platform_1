# BUILD-REQUEST: bronze-options — ROUND 5 (test the anti-join; tests only)

**Builder:** MiMo · **Checkers:** Claude, then DeepSeek
DeepSeek APPROVED the lane (`.agents/deepseek/VERDICT-bronze-options-check.md`) but showed that
removing both the dedup and the anti-join in `_anti_join_new` still leaves **30 passed**. Live data
is correct (0 duplicate keys measured); this round only closes the test gap. **Do not change
production code. Do not run `--write`.**

Add tests that call `_anti_join_new` directly (a small local SparkSession or a stub that mirrors the
DataFrame calls — your choice, but it must exercise the real function):
1. Duplicate keys within the incoming batch are collapsed to one.
2. Keys already present in the target are excluded.
3. Genuinely new keys pass through.

**Prove it:** in a scratch copy under /tmp, remove the `dropDuplicates` and the `left_anti` join (as
DeepSeek did) and show the new tests FAIL; paste that output, then the passing run on HEAD.
Edit only `tests/bronze/test_refresh_bronze_options.py`. LF line endings.
**Commit your work.** Write `.agents/mimo/VERDICT-bronze-options-round5.md`.
