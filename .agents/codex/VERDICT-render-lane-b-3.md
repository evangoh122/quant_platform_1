===CODEX VERDICT START===

CHANGES_REQUESTED

1. MEDIUM — Post-deploy check (a) cannot be performed as documented.

   - [docs/DEPLOYMENT.md:243](/home/jianj/code/qp1-render-b/docs/DEPLOYMENT.md:243) instructs the operator to inspect the keyed IP’s first two octets in logs.
   - [api/main.py:278](/home/jianj/code/qp1-render-b/api/main.py:278) logs only the source mode and Render flag; no request-time keyed-IP logging exists.
   - Either implement the specified privacy-reduced diagnostic or replace check (a) with an actually executable verification. Check (b) does correctly detect the important failure mode where Render preserves attacker-controlled XFF entries before its trusted address.

2. MEDIUM — The startup secret check still permits common credential forms.

   - [api/demo.py:93](/home/jianj/code/qp1-render-b/api/demo.py:93)–[112](/home/jianj/code/qp1-render-b/api/demo.py:112) allows non-empty `AUTHORIZATION`, `BASIC_AUTH`, `SESSION_COOKIE`, `ACCESS_KEY_ID`, `DATABASE_CERT`, and credential URLs such as `CUSTOM_URL=https://host/path?token=secret`.
   - The URL check only recognizes `@` or `://user:` and misses query-string credentials.
   - Add appropriate exact names/suffixes and detect common sensitive URL query parameters. The exact Render allow-list itself is not overly broad; its entries are ordinary Render/runtime metadata.

Verified fixes and attacks:

- The earlier limiter defects are fixed: per-IP rejection occurs before the global bucket, and the single `OrderedDict` remains bounded.
- One client cannot starve the 600/min shared bucket through rejected traffic: it can charge at most its 60/min allowance. Distributed clients can still consume aggregate capacity, as intended.
- Render defaults to `xff_leftmost`; rotating CF/True-Client-IP headers cannot change the key. The remaining Render-XFF premise is clearly disclosed, and post-deploy check (b) detects leftmost-XFF spoofability.
- Demo write routers are absent; all seven `agent.tools_write` entry points reject before side effects. The write-guard tests passed: `7 passed`.
- Demo identity resolution returns the fixed anonymous viewer before reading identity headers.
- Clean demo import and direct GET-handler probes did not import `db.lakebase` or spawn subprocesses.
- `RENDER=true` with demo disabled refuses startup; malformed `PUBLIC_DEMO` values raise.
- Direct SPA attacks covering single/double/triple encoding, backslashes, NUL, external symlinks, symlink loops, long segments/paths, drive syntax, `/assets`, and HEAD routing did not escape the frontend root. Legitimate files remain accessible.
- The generic exception response is `{"detail":"internal error"}` with security headers. Existing targeted tests cover preservation of 404/405/413/429 behavior.

Test limitation:

- The exact command exited immediately because `tests/render` does not exist.
- The fallback `tests/api` and traversal HTTP tests stalled on their first TestClient request in this sandbox. I stopped them and used direct-handler and pure-function probes as permitted.

Mutation proofs in `/tmp`:

- Added a demo POST route → route-surface test failed on the unexpected `POST`.
- Removed the health demo gate → direct mutation test failed because the live credential path was reached and returned `AssertionError` instead of “disabled in public demo.”
- Removed the Render fail-closed guard → `test_render_without_public_demo_refuses` failed because no exception was raised.

No repository files were edited.

===CODEX VERDICT END===
