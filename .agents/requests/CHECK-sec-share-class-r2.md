# CHECK round 2: share-class canonical ticker (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Codex sol r1 finding: .agents/codex/VERDICT-sec-share-class.md (gold emits the canonical's n_chunks on alias rows → tie → alias map re-picked GOOG). Fix e457a63:
07 emits `canonical_ticker`; _load_alias_map reads it directly (identity + WARNING if the column is missing). Claude: 275 passed; READ-ONLY live SELECT of the
new 07 → GOOG 831 canonical GOOGL, GOOGL 831 canonical GOOGL, NVDA→NVDA, BRK.B→BRK.B.
Mutations, each must fail: re-derive canonical in Python from n_chunks; alphabetical fallback when canonical_ticker is missing; 07 canonical by min(ticker).
Test rows must be shaped exactly as 07 emits them (alias rows carry the canonical's n_chunks). Both Spark and warehouse paths read canonical_ticker.
