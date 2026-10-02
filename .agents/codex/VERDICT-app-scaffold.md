# VERDICT: app-scaffold (PR #7) — Codex

CHANGES_REQUESTED

Critical findings:

1. Client-controlled identity enables privilege escalation.

   - `api/deps.py:30-35` trusts several ordinary request headers, including `x-forwarded-user`.
   - `api/deps.py:87-95` accepts their value directly as `user_id`.
   - Missing authentication silently becomes `"default"` at `api/deps.py:36,93`.
   - `_ensure_user()` creates every new identity with the `"trader"` role at `api/deps.py:64-70`.
   - Database failures also fail open to `"trader"` at `api/deps.py:76-78`.

   Thus a caller can select an arbitrary identity through a header—or omit authentication—and receive write authorization. This is not a verified mapping from the authenticated Databricks App principal.

2. Approval identity is client-assertable, and cross-user orders can be approved.

   - `/api/orders/{order_id}/approve` obtains `approver_id` from the insecure header-derived principal at `api/routes/orders.py:67-74`.
   - `record_approval()` loads the order owner at `agent/tools_write.py:231-244`, but never compares it with `approver_id`.
   - It then provisions the asserted approver and records approval at `agent/tools_write.py:256-273`.
   - Placement follows immediately at `api/routes/orders.py:82`.

   Any auto-provisioned “trader” can approve an order belonging to another user if its ID is known.

3. Agent-chat writes bypass role enforcement.

   - Chat uses only `get_current_user`, not `require_role`, at `api/routes/agent_chat.py:95-96`.
   - Watchlist and research-note commands perform writes at `api/routes/agent_chat.py:100-110`.
   - The write tools auto-provision the supplied identity as a trader.

   This permits write operations for unauthenticated/default users and any future non-trader role.

4. Raw exception text is returned to the browser.

   - `_run_tool()` serializes `str(exc)` at `api/routes/agent_chat.py:90-91`.
   - That result is embedded again in user-facing replies at `api/routes/agent_chat.py:103,109,116,133`.

   Database/client exceptions can contain hosts, connection parameters, SQL, or other operational details. Return a stable error code/message and log the underlying exception server-side.

Additional observations:

- Market and signal input handling does not appear SQL/Spark-injectable: symbols are normalized, and `db/delta_adapter.py:83-93` uses Spark column expressions rather than interpolated SQL.
- Gold and analytics empty responses are well formed and carry explicit empty/unavailable freshness states.
- Frontend source contains no TypeScript `any`; API calls are relative `/api` paths. The Vite-only development proxy targets localhost.
- The diff includes `.agents/requests/BUILD-app-scaffold.md` and `.agents/deepseek/VERDICT-app-scaffold.md`, despite `.agents/` being listed under paths not to touch.

Validation:

- `python3 -c 'import api.main'`: PASS
- `cd frontend && npx tsc --noEmit`: PASS
- `git diff --check origin/main...HEAD`: PASS

