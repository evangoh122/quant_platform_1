===CODEX VERDICT START===

# Verdict: CHANGES_REQUESTED

DeepSeek prerequisite: `.agents/deepseek/VERDICT-render-lane-b-check5.md` says **APPROVED**.

## Blocking finding

1. **CRITICAL — Render rate limiting trusts the wrong X-Forwarded-For entry.**

   [api/main.py:148](/home/jianj/code/qp1-render-b/api/main.py:148) selects the rightmost XFF value whenever `RENDER` is set. [docs/DEPLOYMENT.md:193](/home/jianj/code/qp1-render-b/docs/DEPLOYMENT.md:193) claims that value cannot be spoofed, and [tests/api/test_public_demo_security.py:539](/home/jianj/code/qp1-render-b/tests/api/test_public_demo_security.py:539) codifies that assumption.

   Render states that it places the real client IP first in the list. Existing client-supplied XFF values can therefore remain to its right. A client can rotate the rightmost value to:

   - evade the 60-request per-IP limit;
   - churn the bounded LRU continually;
   - consume all 600 global slots and deny service to everyone.

   Sources: [Render’s XFF clarification](https://feedback.render.com/features/p/send-the-correct-x-forwarded-for), [Render’s current client-IP guidance](https://render.com/articles/how-render-handles-ddos-attacks).

   **Required fix:** key on Render’s documented client-IP position, with strict IP parsing and tests representing the actual Render-added chain. Prefer a platform header that Render guarantees overwrites, if formally documented. Remove the incorrect rightmost-entry claims and tests.

   The global ceiling itself remains an intentional shared failure domain: once 600 accepted requests are reached, everyone is denied. After trustworthy IP extraction, a single fixed-IP client cannot exhaust it because per-IP rejection occurs first. Consider a token bucket or reserved per-client capacity so aggregate traffic cannot create a hard minute-long outage.

## Verified fixes and defenses

- The two earlier limiter findings are fixed:

  - [api/main.py:111](/home/jianj/code/qp1-render-b/api/main.py:111): per-IP rejection happens before global charging.
  - [api/main.py:91](/home/jianj/code/qp1-render-b/api/main.py:91): one bounded `OrderedDict` owns per-IP keys and counters.

- Demo write routers are conditionally absent; all seven `agent.tools_write` entry points guard before side effects.
- Demo identity returns the fixed anonymous viewer before reading identity headers or importing Lakebase.
- `/api/health` short-circuits before Lakebase/subprocess access.
- `RENDER` without demo fails closed; unrecognized nonempty `PUBLIC_DEMO` values raise.
- The exact Render allow-list is not excessively broad. Remaining credential-name gaps include generic names such as `TOKEN`, `SECRET`, `PASSWORD`, `DOCKER_AUTH_CONFIG`, and `DATABASE_CONNECTION_STRING`.
- SPA confinement resisted direct probes for single/double/triple encoding, backslashes, NUL, external symlinks, symlink loops, drive paths, and long segments. Legitimate internal files still resolved correctly.
- `/assets` lookup rejected traversal. The SPA catch-all exposes only GET, so HEAD cannot traverse it; the static mount handles legitimate asset HEAD requests.
- The global handler emits only `{"detail":"internal error"}` and security headers. Its registration does not replace Starlette’s more-specific HTTP exception handling, so 404/405/413/429 remain distinct.

## Test execution

The requested command could not start because `tests/render` does not exist:

```text
ERROR: file or directory not found: tests/render
```

The fallback `tests/api` suite stalled on its first TestClient HTTP operation in this sandbox and was interrupted without results. A real uvicorn probe was attempted twice, but this sandbox refused local port binding. Direct `_spa` and `StaticFiles.lookup_path` probes were therefore used, as permitted.

## Mutation proofs in `/tmp`

- Registered a demo POST route: route-enumeration test failed on `/api/mutation-write allows {'POST'}`.
- Removed the health demo gate: the health security assertion failed. The TestClient form stalled, so the handler was tested directly.
- Removed the Render fail-closed condition: `test_render_without_public_demo_refuses` failed because no exception was raised.

The repository was not modified.

===CODEX VERDICT END===
