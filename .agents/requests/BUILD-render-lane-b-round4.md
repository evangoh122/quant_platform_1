# BUILD: Render lane B round 4, Codex review findings (MiMo)

Read `.agents/codex/VERDICT-render-lane-b.md`. Fix both blocking limiter defects, plus the secret-name
gaps. Each fix needs a test that FAILS on the current HEAD (prove it in /tmp).

## 1. [Blocking] One client can exhaust the global ceiling (`api/main.py:~135-146`)
Requests already rejected by the per-IP limit still increment the global counter. Fix the order:
1. check the per-IP limit;
2. if it's over, return 429 WITHOUT touching the global counter;
3. only then check and charge the global counter.

Regression test: one IP sends 10× the global ceiling. Another IP's first request then gets 200.

## 2. [Blocking] The LRU bound doesn't bound `_counts` (`api/main.py:~116-146`)
Use ONE bounded structure, e.g. `OrderedDict[ip] -> (window, count)`, so evicting an IP removes its
counter. No parallel dicts.

Test, with `lru_max=5` and 1,000 distinct IPs:
- the number of stored IPs is ≤ 5;
- the total entries in every internal structure are ≤ 5.

Remove or fix `key_count`, the metric that masked this.

## 3. Broaden the startup secret check (`api/demo.py`)
Also refuse, when the value is non-empty:
- prefixes `AWS_`, `AZURE_`, `GOOGLE_`, `GCP_`, `GITHUB_`, `GH_`, `STRIPE_`, `SENTRY_`;
- suffixes `_DSN`, `_URI`, `_PAT`, `_APIKEY`, `_CREDENTIALS`, `_KEY_BASE`;
- exact names `CREDENTIALS`, `REDIS_URL`, `MONGODB_URI`, `SECRET_KEY_BASE`;
- any `*_URL` whose value contains `@` or `://user:` (credentials embedded in a URL).

Keep the exact-name Render allow-list. One parametrised test per new family. Also include Codex's
examples: `AWS_ACCESS_KEY_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, `GITHUB_PAT`, `REDIS_URL`,
`MONGODB_URI`, `SENTRY_DSN`, `STRIPE_APIKEY`, `SECRET_KEY_BASE`, `AZURE_CLIENT_ID`, `CREDENTIALS`.

## Test runtime note
Codex's sandbox stalls on the first `TestClient` HTTP request, though WSL and CI don't. Keep the
limiter and secret tests as pure-function unit tests where possible, so they run without HTTP.

Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`;
- `CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y python3 -m pytest -q tests/api`;
- both orders with `tests/api/test_rbac.py`.

LF line endings only. Don't touch `.agents/dispatch.sh`. Commit. Update
`.agents/mimo/VERDICT-render-lane-b.md` (round 4).
