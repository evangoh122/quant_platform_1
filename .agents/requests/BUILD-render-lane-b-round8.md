# BUILD: Render lane B round 8, client-IP source (MiMo)

DeepSeek check6 (`.agents/deepseek/VERDICT-render-lane-b-check6.md`) proved that trusting
`CF-Connecting-IP` / `True-Client-IP` FIRST is spoofable whenever Cloudflare doesn't rewrite them.
Rotating the header 200× → 200/200 accepted, and then a real client gets 429. Render's documented
guarantee is: "we set the first IP in the list to the real client IP". Claude's decision:

## Fix
1. Make the source explicit with `CLIENT_IP_SOURCE`, one of `xff_leftmost` (DEFAULT on Render),
   `cf_connecting_ip` or `peer`.
   - `xff_leftmost`: the leftmost `X-Forwarded-For` entry, if it is a valid IP; otherwise
     `request.client.host`. NEVER read the CF/True-Client-IP headers in this mode.
   - `cf_connecting_ip`: only `CF-Connecting-IP` (valid IP); otherwise `peer`. This is opt-in, for
     when Cloudflare is verified in front.
   - `peer`: `request.client.host` only.
   - Outside Render (`RENDER` unset), the default is `peer` and headers are ignored.
   - An unknown value → `PublicDemoConfigurationError` at startup.
   - Add `CLIENT_IP_SOURCE` to the Render allow-list. It's not a secret.
2. `render.yaml` stays on lane A's branch, so don't edit it here. Document in `docs/DEPLOYMENT.md`:
   the default, the reasoning (Render's quote and source URL), and the **post-deploy verification**
   to run before going public:
   - (a) send `X-Forwarded-For: 1.2.3.4` from one machine, and check which IP the limiter keys on
     (log only the first two octets);
   - (b) from one machine, send 70 requests with rotating spoofed XFF, CF-Connecting-IP and
     True-Client-IP headers, and confirm that request 61 gets 429;
   - (c) if (b) fails, switch `CLIENT_IP_SOURCE`.
3. Add a debug-safe log line at startup with the active `CLIENT_IP_SOURCE`.

## Tests, each failing on the current HEAD (prove it in /tmp)
- Default on Render: rotating `CF-Connecting-IP` with a fixed leftmost XFF → ONE key, and request 61
  gets 429.
- Rotating `True-Client-IP` → ignored.
- The leftmost XFF entry is an invalid string → falls back to `client.host`.
- `cf_connecting_ip` mode → uses CF.
- `peer` mode → ignores every header.
- An unknown mode → startup error.

Run:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`;
- the same suite with `CLAUDE_CODE_MESSAGING_TOKEN=x DATABRICKS_WORKSPACE_ID=y` set.

LF line endings only. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Commit with a
descriptive message. Update `.agents/mimo/VERDICT-render-lane-b.md` (round 8).
