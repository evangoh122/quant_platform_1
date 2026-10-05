# CHECK: share-class canonical ticker (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Spec .agents/requests/BUILD-sec-silver-share-class.md (the re-spec; an earlier wrong attempt was reset). Commits e0defee (07 SQL), 6584cb3 (alias map),
635c321 (tests). Claude: 269 passed; READ-ONLY live run of the new 07 SELECT → GOOG 831, GOOGL 831 (were 0/0), 230 covered tickers (was 228); BRK.B 517,
BRK.A 0 with empty CIK (BRK.A has no mapped CIK — out of scope? judge).
1. Mutations: revert 07 to `min(ticker)` → test fails; revert _load_alias_map to `sorted()[0]` → test fails.
2. The SQL and the alias map pick the SAME canonical for every CIK (tie-break identical); single-ticker CIKs unchanged; SQL has no user input.
3. check_ticker_coverage('GOOG') / ('GOOGL') both succeed with the fake; retrieval for an alias loads the canonical's corpus.
4. Offline suite `python3 -m pytest -q -m "not spark and not lakebase and not databricks"`.
