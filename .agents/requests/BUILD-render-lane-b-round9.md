# BUILD: Render lane B round 9, Codex review (MiMo)

Read `.agents/codex/VERDICT-render-lane-b-3.md`. Two MEDIUM findings; everything else was verified.

1. **Post-deploy check (a) can't actually be run.** `docs/DEPLOYMENT.md:~243` says to inspect the
   keyed IP's first two octets in the logs, but nothing logs it.
   - Add an opt-in diagnostic: when `RATE_LIMIT_DEBUG=1`, log one line per request with the
     `CLIENT_IP_SOURCE` mode and a privacy-reduced key: IPv4 → first two octets + ".x.x"; IPv6 → the
     first 2 hextets + "::/32".
   - It is off by default. Never log full IPs or header values.
   - Add `RATE_LIMIT_DEBUG` to the Render allow-list.
   - Update the docs so check (a) says: turn it on, send `X-Forwarded-For: 1.2.3.4`, confirm the
     logged key is NOT "1.2", turn it off.
   - Tests: off → no per-request log line; on → the redacted format, and no full IP in the output.
2. **The secret check misses common credential forms** (`api/demo.py:~93-112`). Refuse when non-empty:
   - exact names `AUTHORIZATION`, `BASIC_AUTH`, `SESSION_COOKIE`;
   - suffixes `_ACCESS_KEY_ID`, `_CERT`, `_COOKIE`, `_AUTH`;
   - any env value that is a URL with a sensitive query parameter (`token`, `key`, `apikey`,
     `api_key`, `secret`, `password`, `pwd`, `sig`, `signature`, `access_token`, `auth`), matched
     case-insensitively.

   Keep the exact Render allow-list. Parametrised tests for every new pattern, including
   `CUSTOM_URL=https://host/path?token=secret`. Also check for false positives on harmless URLs
   (`?page=2`) and on Render defaults.

Each new test must FAIL on the current HEAD (prove it in /tmp). Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`;
- the same suite with `CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y` set.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Commit with a
descriptive message. Update `.agents/mimo/VERDICT-render-lane-b.md` (round 9).
