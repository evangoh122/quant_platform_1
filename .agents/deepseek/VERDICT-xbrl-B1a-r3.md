===VERDICT START===
# VERDICT: xbrl-B1a-r3 — DeepSeek (checker)
**Status:** CHANGES_REQUESTED
**Round:** 3

## Blocking findings

- [pipelines/sec_rag_ingest.py:189] `_validate_user_agent` raises a `ValueError` whose
  message interpolates `repr(user_agent)` — the full User-Agent string, which embeds the
  contact email. Confirmed live:
  `_validate_user_agent("Sample Company Name AdminContact@<sample company domain>.com")`
  → `... Got: 'Sample Company Name AdminContact@<sample company domain>.com'`.
  This violates the spec (BUILD-xbrl-B1a.md:14 "Never log ... the contact email") and the
  `_resolve_user_agent` docstring's own promise ("Never logs/prints the actual value").
  It is a regression introduced by MiMo's round-3 commit 6d4413c (the too-loose-UA fix).
  An invalid-but-close UA (e.g. missing TLD) still carries a real contact email, so the
  exception — logged by the failing job — leaks it.

- [tests/bronze/test_sec_companyfacts.py:737] The required "seen_payloads marked before
  the write" mutation does NOT fail a test. `test_first_write_failure_allows_second_write`
  maps two tickers to the same CIK and drives them through
  `ThreadPoolExecutor(max_workers=2)`. Both threads pass the `seen_payloads` membership
  check (pipelines/ingest_sec_companyfacts.py:455) before either reaches the `add`
  (:485), so moving the `add` to before the write produces the identical outcome.
  Verified: mutated `add` to before `delta_writer` → the test still passes 10/10 runs.
  The request's acceptance criterion ("seen_payloads marked before the write → FAIL") is
  unmet, and the test does not prove the fix it claims to guard.

## Confirmed fixed (Codex's 4 blocking items)

- [pipelines/sec_rag_ingest.py:844] 403 is now in the retryable set `(403, 429, 503)`
  with bounded exponential backoff + Retry-After honouring. Mutation (drop 403) → 3 tests
  fail.
- [pipelines/sec_rag_ingest.py:182-190] UA now requires `<name> <email>`. Accepts
  `"quant-platform research evangohsg@gmail.com"` and `"MyApp/2.0 contact@company.com"`;
  rejects `"foo"`, `"foo bar"`, `"a@b.com"`, and
  `"Sample Company Name AdminContact@<sample company domain>.com"`. Mutation (remove the
  format check) → 4 tests fail.
- [pipelines/ingest_sec_companyfacts.py:95-109,273,663,680-697] manifest now carries
  `http_status` (int, last response status per CIK; null if none). Mutation (remove the
  two `manifest.http_status` assignments) → 2 tests fail.
- [pipelines/ingest_sec_companyfacts.py:483-487] `seen_payloads.add` is correctly after
  the Delta write. Code is right; only its mutation-proof test is ineffective (above).

## Non-blocking notes (round-3 spec "do them" — NOT actually done)

- [pipelines/ingest_sec_companyfacts.py:444,448,498,518] `attempt_count =
  client.request_count - req_before` still uses a SHARED `SecClient` counter while
  fetches run concurrently. Codex's non-blocking item and the spec's "per-CIK
  attempt_count (thread-local or returned from the fetch call, not a shared counter)" are
  NOT fixed — concurrent fetches contaminate each other's count.
- [pipelines/ingest_sec_companyfacts.py:454-461] The `skipped_duplicate` manifest branch
  never assigns the computed `attempt_count`, so duplicates keep the dataclass default
  `1` — spec's "duplicate manifests carry the computed attempt_count" NOT fixed.
- [tests/bronze/test_sec_companyfacts.py:1062] `test_bounded_concurrency_max_workers`
  still asserts only `mapped_count/fetched_count/total_facts == 6`, never `max_workers <=
  4` — spec's "concurrency test asserts max_workers <= 4" NOT fixed.
- MiMo's `.agents/mimo/VERDICT-xbrl-B1a-r3.md` APPROVED verdict is a self-report that
  overstates completion: 3 of the 4 non-blocking items it was asked to "do" are not done,
  and it did not catch the email-leak regression its own round-3 commit introduced.

## Checks run

- `python3 -m pytest tests/bronze/test_sec_companyfacts.py tests/rag/test_sec_rag_ingest.py -q` → **255 passed**
- `python3 -m pytest -q -m "not spark and not lakebase and not databricks"` → **2490 passed, 107 skipped, 24 deselected** (220.65s)
- UA accept/reject matrix (inline script) → 2 accept OK, 4 reject OK; rejection messages confirm the `repr(user_agent)` leak
- Mutation "drop 403 from retry set" → **3 failed**
- Mutation "move `seen_payloads.add` before `delta_writer`" → **0 failed** (test passes 10/10) ← ineffective
- Mutation "remove `<name> <email>` format check" → **4 failed**
- Mutation "remove `manifest.http_status` assignment" → **2 failed**
- SQL review (ROLE mandate): only `CREATE TABLE IF NOT EXISTS` DDL with `{catalog}.{schema}` identifiers; no WHERE filters, no interpolated values; writes are append-mode — no injection violation.
===VERDICT END===
