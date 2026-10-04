===VERDICT START===
# VERDICT: nl1-round20 — DeepSeek (checker)
**Status:** APPROVED
**Round:** 20

Verified MiMo's round-20 build (`ba68801`) against the two Codex Medium findings from `.agents/codex/VERDICT-nl1-review5.md`. Source read-only; every mutation performed in `/tmp/qp1-nl1-r20` and `/tmp/qp1-nl1-old` copies created via `git archive HEAD | tar -x -C /tmp/<dir>`. Working tree untouched by this check (only the pre-existing `.agents/dispatch.sh` modification remains uncommitted, unrelated to this slice).

## Blocking findings

None.

## Codex probes rerun (all pass)

Probe script (`/tmp/qp1-nl1-r20/probe_r20.py`) mutates the production YAML in the archive copy and asserts the loader raises the correct exception type:

| Probe | Expected | Result |
|---|---|---|
| policy: `hard_bounds.gold.rogue_bound` (unknown nested key) | `PolicyValidationError` | PASS |
| policy: `hard_bounds.gold = 42` (malformed mapping) | `PolicyValidationError` (not AttributeError) | PASS |
| policy: `hard_bounds.gold = [1,2]` | `PolicyValidationError` | PASS |
| policy: missing `hard_bounds.gold.date_bound_years` | `PolicyValidationError` | PASS |
| policy: missing `soft_thresholds.cheap.max_days` | `PolicyValidationError` | PASS |
| policy: `soft_thresholds.cheap = "oops"` | `PolicyValidationError` | PASS |
| policy: unknown top-level key | `PolicyValidationError` | PASS |
| policy: `hard_bounds.silver.rogue_bound` | `PolicyValidationError` | PASS |
| registry: `semantic_registry_version = "999.0.0"` | `RegistryValidationError` | PASS |
| registry: `policy_version = "999.0.0"` | `RegistryValidationError` | PASS |
| registry: `semantic_model_version = "999.0.0"` | `RegistryValidationError` | PASS |
| registry: unknown grouping token `bogus_grouping` | `RegistryValidationError` | PASS |
| registry: `entity_count.default = "oops"` vs int bounds | `RegistryValidationError` (TypeError not suppressed) | PASS |

## Mutation-reverting tests FAIL on old code

Staged `7e742c7` (pre-fix) `analytics_nl/policy.py` + `analytics_nl/registry.py` in an archive copy and ran the new test classes:

```
python3 -m pytest tests/analytics_nl/test_policy.py::TestFailClosedKeySets \
                     tests/analytics_nl/test_registry.py::TestRegistryFailClosed -q
→ 13 failed, 14 passed
```

The 13 failures are exactly the regression guards: 5 unknown-key tests, 3 malformed-mapping tests (fail on old code with `AttributeError` — the construction dereference ran before `if errors: raise`), 2 version-mismatch tests, 1 grouping-token test, 2 TypeError-suppression tests. Matches MiMo's claim of "13 fail on old code".

## Checks run

- `python3 -m pytest tests/analytics_nl -q` → **437 passed** in 18.73s
- `python3 -m analytics_nl.export_schemas --check` → **All schemas match.**
- `python3 probe_r20.py` (13 mutation probes + 2 load sanity checks) → **ALL PROBES PASS**

## Non-blocking notes

- The four "missing key" tests (`test_missing_gold_key_raises_policy_error`, `test_missing_cheap_max_days_raises_policy_error`, `test_missing_hard_bounds_raises_policy_error`, `test_missing_soft_thresholds_raises_policy_error`) also pass on the old code, because the old loader already raised via the `if val is None → "required"` branch before construction. The default-substitution removal (`policy.py` construction now uses direct `dict[...]` access) is therefore defense-in-depth, not a fix for an actively-exploitable silent default — the old defaults (`gold_raw.get("date_bound_years", 10)`, etc.) were already unreachable in the fail path. Valid fail-closed assertions, but not regression-distinguishing.
- `registry.py` `_parse_entry` still uses direct `raw["layer"]` / `raw["serving_view"]` / `raw["aggregation"]` access; safe because `_validate_registry` runs first and rejects missing/invalid values. A non-dict entry value would still `AttributeError` inside `_validate_registry` (`entry_raw.get(...)`) — pre-existing, out of scope for this round.
- `_VALID_GROUPING_TOKENS` = `{g.value for g in Grouping}` (day/week/month/quarter/year/ticker/sector) covers every `allowed_grouping` value in the production registry; `_VALID_AGGREGATION_TOKENS` likewise covers all ten production aggregation tokens. No false rejections.
===VERDICT END===
