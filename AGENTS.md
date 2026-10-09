# Agent workflow

This file is the repository's single source of truth for delegated changes.

## Required chain

1. **MiMo implements** from a scoped `BUILD-*.md` request.
2. **DeepSeek independently validates** the exact committed SHA and returns
   `APPROVED`, `CHANGES_REQUESTED`, or `FAILED`.
3. **Codex performs final validation** only after DeepSeek approves that exact SHA.
4. Open or update the PR and immediately comment `@coderabbitai review`.
5. Any valid CodeRabbit finding returns to MiMo and restarts DeepSeek → Codex.

MiMo's report is a builder self-report, never independent approval. Any later
commit invalidates DeepSeek and Codex results. Do not substitute Claude, Kimi,
GPT, or another model for DeepSeek when DeepSeek is unavailable or cannot be
positively identified; report the gate as blocked.

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

## Pull requests and authority

After opening or updating every PR, run:

```bash
gh pr comment <PR_NUMBER> --body "@coderabbitai review"
```

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
