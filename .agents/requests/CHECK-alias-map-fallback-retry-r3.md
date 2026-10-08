# CHECK round 3: alias-map fallback retry — re-check of your r2 finding (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Your r2 verdict: .agents/deepseek-fallback/VERDICT-alias-map-fallback-retry-r2.md (reload_corpus did not declare `_alias_map_loading` global). Fix: the latest fix commit (Claude tiny fix + test
`test_full_reload_corpus_resets_alias_map_loading_flag`). Claude: 148 passed; dropping the global → the new test fails. Repeat that mutation and your earlier ones (cache-forever per branch,
in-flight guard removed, concurrency ≥4 threads → one read).
