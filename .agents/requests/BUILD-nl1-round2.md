# BUILD: NL1 round 2 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit after each step. NEVER delete or weaken
> existing tests.

Round 1 is committed (144 tests pass), but it predates the owner's amendment and contains NO
`put_call_ratio` (grep finds 0 matches). Implement
`.agents/requests/BUILD-nl1-amendment-put-call.md` in full:
- the 9th metric `put_call_ratio`, from `gold_options_features.put_call_ratio`, via an approved
  options serving view, with DDL in the docs appendix;
- aliases: "put/call", "put call ratio", "PCR", "p/c ratio";
- aggregation: MEAN, never sum. "Sum of put call ratio" is rejected or coerced with a disclosed
  assumption, and tested;
- regenerate the JSON schemas, and keep the sync test passing;
- mark the 8th/9th-metric owner decision as RESOLVED.

New tests must fail on the current HEAD (prove it in /tmp). Run `python3 -m pytest -q
tests/analytics_nl` and the full suite with `--ignore=tests/lakebase`. LF line endings only. Don't
touch `.agents/dispatch.sh`. Update `.agents/mimo/VERDICT-nl1-contracts.md` (round 2).
