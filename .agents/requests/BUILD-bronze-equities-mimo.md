# BUILD-REQUEST: bronze-equities — reassigned to MiMo

DeepSeek started this lane and stopped when its account ran out of credit.
**Nothing was written to any bronze table** (coordinator verified: row deltas are +0).

Your full lane spec is `.agents/requests/BUILD-bronze-equities.md` (read it first) and the plan is
`docs/BRONZE_REFRESH_PLAN.md`. Continue from what is already in this branch:


Extra rules learned so far:
- **Do not upload or create files in the Databricks workspace** (a previous attempt created
  `/Users/.../qp1/probe.py`; it was cleaned up). Run locally via databricks-connect serverless.
- Write files with **LF line endings**, not CRLF. Do not modify `.agents/dispatch.sh`.
- Run `--dry-run` and paste its report before `--write`. Bronze is append-only.
- **Commit your work** to `slice/bronze-equities` and write `.agents/mimo/VERDICT-bronze-equities.md`.
