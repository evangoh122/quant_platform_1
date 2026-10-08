# CHECK: alias-map fallback retry (follow-up to merged PR #43) (checker; Codex luna while DeepSeek is out of balance)

Read-only; mutations only in /tmp copies made with `git archive HEAD`. Print the verdict to stdout between ===VERDICT START=== / ===VERDICT END===,
"Status: APPROVED" or "Status: CHANGES_REQUESTED", file:line.
Specs: .agents/requests/BUILD-alias-map-fallback-retry.md, -r2.md. Commits dade365 (retry deadline instead of cache-forever), 806bb45 (tests for all three fallback branches).
Claude: 145 passed; missing-column branch reverted to `_alias_map_loaded = True` → 1 failed (it survived round 1).
Mutations, each must fail: cache-forever on each of the three branches (missing column, no rows, generic exception); drop the deadline check (re-read every call); re-read a successful load.
Thread safety: only one caller reloads after the deadline; the lock is held when publishing the map; reload_corpus() invalidation still works. Tests call only production code.
