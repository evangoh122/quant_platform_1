# BUILD-REQUEST: app-scaffold — ROUND 2 (authentication & error handling)

**Branch:** `slice/app-scaffold` · **Builder:** DeepSeek · **Validators:** Claude, then Codex
**Gate:** PR #7 BLOCKED. Read `.agents/codex/VERDICT-app-scaffold.md`.

The scaffold, routes, frontend and empty-state handling are good — keep them.
The defects are in identity and error handling.

## 1. Identity must come from the Databricks App proxy only (critical)

Today `api/deps.py:30-35` tries four headers, including `x-forwarded-user` and
`x-databricks-user`, falls back to `"default"` when none is present (`:36,93`),
and provisions every new identity as `trader` (`:64-70`). A database error
also falls back to `trader` (`:76-78`).

Fix:
- Trust **one** header: the identity the Databricks Apps proxy sets
  (`x-forwarded-email`, overridable by `AUTH_USER_HEADER`). Drop the others.
- **No silent default user.** If the header is absent → `401`, unless
  `APP_ENV=dev` is set explicitly, in which case use `AUTH_DEV_USER`. Production
  must never fall through to a dev identity.
- **deps.py must never assign a role.** Read the role from `users`. An unknown
  user is provisioned as `viewer` (non-approving). Approver authority is granted
  out-of-band — a concurrent lane is adding `scripts/grant_approver.py` and a
  migration that makes `viewer` the default.
- **Fail closed.** A database error in auth/role lookup returns `503`, never a
  role.
- Write routes (`watchlists POST`, `orders/*`, and the agent-chat paths that
  write) require an authenticated, non-dev-fallback user, and order approval
  requires the approver role. `api/routes/agent_chat.py:95-110` currently writes
  with only `get_current_user` — add the role check.
- `/api/orders/{id}/approve` must pass the **authenticated** user as approver.
  Never read approver identity from the body, query, or any other header.

## 2. No raw exception text to the browser

`api/routes/agent_chat.py:90-91` serialises `str(exc)` into responses
(re-embedded at `:103,109,116,133`). Return a stable error code and generic
message; log the exception server-side. Audit every route for the same pattern
(`str(e)`, `repr(e)`, f-strings containing exceptions in responses).

## 3. Tests — add `tests/api/`

Use FastAPI `TestClient` with the Lakebase and Spark dependencies overridden.
Tests that must exist:
- No auth header in prod mode → `401`.
- A spoofed `x-forwarded-user` / `x-databricks-user` with no `x-forwarded-email` → `401`.
- New user → `viewer` → order approve → `403`.
- Simulated DB failure in role lookup → `503`, not success.
- A route whose backend raises → response body contains no exception text.

## Constraints

- **Do not edit `agent/` or `db/`.** The lakebase lane is changing them; this
  branch will be rebased onto it afterwards. Code against the public
  signatures `record_approval(order_id, ApprovalContext)` and
  `approve_and_place_paper_order(order_id)`.
- Do not touch `ml/`, `silver/`, `gold/`, `conftest.py`, `pytest.ini`, `requirements.txt`.
- `python3 -c "import api.main"`, `cd frontend && npm run build` and
  `python3 -m pytest tests/api -q` must pass. Paste all three.
- **Commit your work.** Write `.agents/deepseek/VERDICT-app-scaffold-round2.md`.
