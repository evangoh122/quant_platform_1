# Agent workflow

This file is the repository's single source of truth for delegated changes.

## Required chain

1. **MiMo implements** from a scoped `BUILD-*.md` request.
2. **DeepSeek independently validates** the exact committed SHA and returns
   `APPROVED`, `CHANGES_REQUESTED`, or `FAILED`.
3. **One final gate, chosen by complexity**, runs on the exact SHA after
   DeepSeek approves: **Codex Sol** for simple/routine changes, **Opus 5.5**
   (`claude-opus-5-5`) for complex changes or any escalation trigger (see
   "Reviewer selection and escalation"). Exactly one final gate per head SHA.
4. Open or update the PR (CodeRabbit is requested per the CodeRabbit rules
   below).
5. Valid CodeRabbit findings return to MiMo and restart steps 2–3.
6. After CI and CodeRabbit are clean the owner authorizes the merge (or has
   pre-authorized it for named PRs).

MiMo's report is a builder self-report, never independent approval. Any later
commit invalidates DeepSeek, Codex Sol and Opus results. Codex Sol and Opus
5.5 are alternative final gates, never substitutes for DeepSeek. Do not
substitute Claude, Kimi, GPT, or another model for DeepSeek when DeepSeek is
unavailable or cannot be positively identified; report the gate as blocked.

## Reviewer selection and escalation

Codex Sol (currently `gpt-6.1-sol`, the owner's "GPT-6.1 Sol"; the model slug
may change with Codex releases) is the final gate for simple, routine changes.
Opus 5.5 (`claude-opus-5-5`) is the final gate for complex changes: use it when
at least one of the following applies, or when the coordinator judges the change
too complex for a routine check (record the reason):

1. **Critical core architecture**: renames/moves modules, changes public
   interfaces, or touches 3+ top-level packages.
2. **Database schemas and data contracts**: `db/migrations/**`,
   `db/schema_contract.py`, `api/schemas.py`, table/view definitions under
   `bronze/`, `silver/`, `gold/`, `sql/`.
3. **Payment-gateway equivalent** — order placement, approvals, guardrails and
   broker/execution code: `api/routes/orders.py`, `agent/guardrails.py`,
   `agent/tools_write.py`, `execution/**`, anything handling credentials,
   authentication/roles or approvals; also deployment/security configuration:
   `api/deps.py`, `api/demo.py`, `db/lakebase.py`, `security/**`,
   `.github/**`, `app.yaml`, `databricks.yml`, `resources/**`, `render.yaml`,
   `requirements*.txt`. This list is non-exhaustive.
4. **A release or submission-candidate merge**, or any change to
   deployment/production configuration.

This repository has no integration branch; every PR targets `main` directly, so
merging into `main` is not by itself an escalation trigger. A change that
triggers none of the above uses Codex Sol as its single final gate; a change
that triggers any of them uses Opus 5.5 as its single final gate. Neither
substitutes for DeepSeek.

The coordinator records the reviewer used and the trigger in the PR description.
Opus is read-only (never edits, commits, pushes, or deploys), must be positively
identified, and returns one terminal line:

```text
OPUS FINAL | verdict: <APPROVED|CHANGES_REQUESTED> | sha: <40-char SHA>
```

Codex Sol returns:

```text
CODEX FINAL | verdict: <APPROVED|CHANGES_REQUESTED> | sha: <40-char SHA>
```

A missing or incomplete report is failure, not approval.

## Build requests and evidence

Every build request must specify numbered file/line changes, acceptance
commands, tests that fail on the old behavior, required mutation proofs, LF line
endings, non-goals, a commit requirement, and a verdict path. Use isolated
`git archive` copies under `/tmp` for old-behavior and mutation proofs; never
copy a worktree recursively.

Run MiMo from the intended worktree:

```bash
timeout 7500 ./.agents/dispatch.sh mimo .agents/requests/BUILD-<topic>.md 7200 < /dev/null
```

Run DeepSeek against the exact MiMo commit with a scoped validation request:

```bash
timeout 7500 ./.agents/dispatch.sh deepseek .agents/requests/VALIDATE-<topic>.md 7200 < /dev/null
```

After every run restore the dispatcher, make it executable, and verify the
branch, HEAD ownership, worktree status, and unexpected files. Preserve
unrelated user changes.

MiMo must emit exactly one terminal report after its evidence file is readable:

```text
BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-character SHA or NO_COMMIT> | branch: <branch> | evidence: <path>
```

DeepSeek must emit exactly one terminal report after its evidence artifact is
written and verified readable:

```text
VALIDATION DONE | verdict: <APPROVED|CHANGES_REQUESTED|FAILED> | sha: <40-character SHA or SHA_NOT_VERIFIED> | evidence: <path>
```

A timeout, crash, missing field, missing terminal report, skipped/vacuous test,
or unintended worktree change is failure—not approval. Worker timeout is 7200
seconds; the outer guard is 7500 seconds so evidence can flush.

## Validation requirements

DeepSeek and Codex must identify and validate the exact SHA, inspect the diff,
run the relevant tests independently, and reproduce the important old-behavior
and mutation proofs. Codex may start only after a readable DeepSeek `APPROVED` report
for the current SHA. Findings must include file:line and concrete test evidence.

### CI parity (standing rule)

CI runs `pytest -q -m "not spark and not lakebase and not databricks"` with NO
pyspark installed (`.github/workflows/ci.yml`) while developer machines may
have pyspark, so tests can pass locally and fail CI. Every acceptance run must
execute that exact command both normally and with pyspark blocked via a stub
package that raises `ModuleNotFoundError("No module named 'pyspark'")` placed
first on `PYTHONPATH` in a temp directory outside the repo; tests must not
require pyspark. No hard-coded home-directory paths.

## Pull requests and authority

After pushing commits that passed DeepSeek and Codex Sol to an existing PR
(never at PR open — the workflow below already requests that review), run:

```bash
gh pr comment <PR_NUMBER> --body "@coderabbitai review"
```

The workflow `.github/workflows/coderabbit-trigger.yml` already posts
`@coderabbitai review` when a PR is opened, reopened, or marked ready — do NOT
also comment manually at open. Comment `@coderabbitai review` manually only
after pushing commits that have passed DeepSeek and Codex Sol, and only if no
automatic request (open, reopen, ready-for-review) already covers the current
head SHA. Use
`@coderabbitai full review` only when needed (e.g. after merging main/rebasing,
or when the incremental review answers "already reviewed" although the
changeset effectively changed).

The owner's budget is 5 CodeRabbit reviews per hour: batch fixes, never loop
or retry-poll, record which PR gets the next slot.

If the comment fails, do not loop or bypass restrictions. Report exactly:

```text
CODERABBIT_TRIGGER_NEEDED: PR #<number>
```

Never push directly to `main`. Never merge, deploy, rebuild shared tables,
retrain models, or write shared signals without separate owner approval.

## Credentials and cleanup

Use only already-configured credentials. Never read, print, copy, persist, or
pass credential files, API-key environment values, or secrets in prompts,
commands, logs, commits, or verdicts. Do not inspect credential files merely to
confirm credentials exist.

Use explicit worktree and temporary paths. Never use `$HOME`, `~`, a repository
root, unresolved globs, or broad recursive targets for destructive operations.
Do not use `pkill -f`.

## Windows and WSL boundary

First identify the executing shell. In native WSL/Linux, run Linux commands
directly and never invoke `wsl.exe`.

When OpenCode is hosted by Windows, never run repository commands through
inline `wsl ... bash -c`, nested `wsl.exe`, UNC or mapped-drive working
directories, CMD/PowerShell wrappers, `Start-Process`, `ProcessStartInfo`,
`.ps1`/`.bat` helpers, or Windows Node/npm/npx.

The only sanctioned Windows-to-WSL route is an LF Bash script inside the WSL
worktree at `.agents/run-<task>-<round>.sh`, invoked directly as:

```text
wsl.exe -d Ubuntu -- bash /absolute/linux/worktree/.agents/run-<task>-<round>.sh
```

Capture output to a log beside the script and inspect the exit code. Prefer an
existing repository acceptance script. After one failed boundary invocation,
stop the round and report `FAILURE`; do not try alternate wrappers or quoting.
Never install or migrate agent runtimes or copy provider configuration without
explicit owner approval.
