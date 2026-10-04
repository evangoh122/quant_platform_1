# BUILD: NL1 round 7 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. NEVER delete or weaken existing
> tests.

Checker verdict: `.agents/deepseek/VERDICT-nl1-contracts-check4.md`, written by the Claude checker
because DeepSeek is out of credit. Read it fully. 3 blocking issues:

1. **`LLMEntityMention.text` is a blacklist** (`contracts.py:~299-311`). It accepts SQL without
   metacharacters, control/zero-width/bidi characters, `<script>`, `$(…)`, `{{…}}`, `${jndi:…}`,
   URLs, fullwidth or Greek semicolons, and reworded injections. Replace it with an ALLOWLIST:
   - NFKC-normalise first;
   - then require `^[A-Za-z0-9][A-Za-z0-9 .&'\-/]{0,59}$` (ticker or company-name characters only;
     widen ONLY if a real alias needs it, and justify it);
   - reject anything else;
   - emit the same `pattern` in the JSON schema.

   Tests: every payload from the verdict is rejected; real aliases from `aliases_v1.yaml` (including
   "AT&T"-style names) are accepted.
2. **`resolve_relative_date` ignores the timezone** (`aliases.py:~232`). It uses
   `clock.now().date()`. Use `clock.now().astimezone(ZoneInfo("America/New_York")).date()`, and
   reject a naive clock. Tests: 2026-03-09 02:00 UTC → NY 2026-03-08, for both `ytd` and
   `last_year` at 2026-01-01 03:00 UTC.
3. **A real fuzz/audit test:**
   - (a) a schema-walking test enumerates EVERY string leaf of `LLMIntentOutput`, and asserts each is
     an enum, an ISO date, or has an allowlist `pattern`;
   - (b) a hostile corpus of ≥ 60 payloads (SQL, shell, template, JNDI, URL, control/zero-width/bidi,
     homoglyph, multilingual injection) is injected into every string leaf, and all are rejected.

   Mutation proofs in /tmp:
   - loosening `LLMEntityMention.text` back to the blacklist must fail (b);
   - adding a new free `str` field must fail (a).

Regenerate the schemas. Run `python3 -m pytest -q tests/analytics_nl` and the full suite with
`--ignore=tests/lakebase`. LF line endings only. Don't touch `.agents/dispatch.sh`. Update
`.agents/mimo/VERDICT-nl1-contracts.md` (round 7).
