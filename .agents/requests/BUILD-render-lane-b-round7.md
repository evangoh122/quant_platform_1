# BUILD: Render lane B round 7, client-IP extraction (MiMo)

Codex re-review (`.agents/codex/VERDICT-render-lane-b-2.md`), CRITICAL: the limiter keys on the
RIGHTMOST `X-Forwarded-For` entry when `RENDER` is set (`api/main.py:~148`). Render staff state:
"we set the first IP in the list to the real client IP"
(https://feedback.render.com/features/p/send-the-correct-xforwardedfor, marked complete 2021-05-28).
Render users report that client-supplied XFF values are not stripped. Render traffic passes through
Cloudflare, which sets `CF-Connecting-IP` / `True-Client-IP` itself. So a client can rotate the
rightmost value to evade per-IP limits, churn the LRU, and fill the global ceiling.

## Fix: `client_ip(request)`, used only when `RENDER` is set
Use the first match in this order:
1. `CF-Connecting-IP`, if present and a valid IP (`ipaddress.ip_address`). Set by Cloudflare.
2. `True-Client-IP`, if present and valid.
3. The LEFTMOST entry of `X-Forwarded-For`, if it is a valid IP (Render's documented position).
4. Otherwise `request.client.host`.

Rules:
- Parse strictly. Strip whitespace. Reject anything that isn't a valid IPv4/IPv6 address; on
  rejection, fall to the next source. Normalise IPv6 (and IPv4-mapped IPv6).
- Outside Render, use `request.client.host` only and ignore every header.

Also:
- **Shared ceiling:** replace the hard global ceiling with a token bucket, so aggregate load causes
  brief 429s and never a minute-long outage. Or reserve capacity, e.g. the global ceiling applies only
  to clients already above half their per-IP quota. Document the choice.
- **Generic secret names:** extend the startup check to the bare names `TOKEN`, `SECRET`,
  `PASSWORD`, `DOCKER_AUTH_CONFIG`, and the suffix `_CONNECTION_STRING`.
- **Docs and tests:** delete the incorrect "rightmost cannot be spoofed" claim in `docs/DEPLOYMENT.md`
  and its test. Document the order above, and add a post-deploy check to the release rehearsal: from
  two machines, send 70 requests each with rotating spoofed XFF values, and confirm each machine is
  limited independently.

## Tests, each failing on the current HEAD (prove it in /tmp)
- `RENDER` set, `CF-Connecting-IP: 1.1.1.1`, with rotating XFF values → every request uses one key,
  so the 61st request gets 429.
- No CF header, `X-Forwarded-For: 2.2.2.2, <rotating junk>` → the key is 2.2.2.2.
- A spoofed invalid value (`CF-Connecting-IP: abc`) → falls back to the next source.
- Outside Render, headers are ignored.
- The token bucket: aggregate load never blocks a fresh client for longer than one refill interval.

Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`;
- the same suite with `CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y` set.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Commit with a
descriptive message. Update `.agents/mimo/VERDICT-render-lane-b.md` (round 7).
