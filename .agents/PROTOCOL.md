# Multi-agent build & verify protocol — quant_platform_1

Four agents run as separate CLIs with no shared memory. They coordinate through
files in this repo. Ported from the Rag_workbench protocol.

## Agents, lanes, and verified routes

| Agent    | Lane                                               | Route (verified working)              | Verdict file                   |
| :------- | :------------------------------------------------- | :------------------------------------ | :----------------------------- |
| DeepSeek | **Builder** + API contracts, schemas, SQL routes   | `deepseek/deepseek-v4-pro`            | `.agents/deepseek/VERDICT-<f>.md` |
| MiMo     | **Builder** + performance, DB cost, indexing       | `xiaomi-token-plan-sgp/mimo-v2.5-pro` | `.agents/mimo/VERDICT-<f>.md`     |
| Codex    | **Validator** — correctness, security, tests       | `codex exec`                          | `.agents/codex/VERDICT-<f>.md`    |
| Claude   | **Coordinator + Validator** — architecture, gating | (this session)                        | `.agents/claude/VERDICT-<f>.md`   |

Broken routes — do not use: `mimo/*` (literal `BASE_URL` placeholder in
`~/.config/opencode/opencode.json`), `xiaomi/*` (insufficient account balance),
`opencode/mimo-v2.5-free` (upstream error).

## Roles

Builders write code. Validators do not write feature code; they read the diff
and return a verdict. Claude never hand-writes a slice that a builder can do —
coordination and gating only.

## Message types

1. **BUILD-REQUEST** → `.agents/requests/BUILD-<feature>.md`
   Written by Claude. Contains: scope, exact files to create/modify, acceptance
   criteria, and explicit non-goals.
2. **VERDICT** → each agent's lane file above. Format below.
3. **SUMMARY** → `.agents/requests/SUMMARY-<feature>.md`
   Written by Claude once all verdicts are in. Sets the gate.

## Verdict format

```markdown
# VERDICT: <feature> — <AGENT>
**Status:** APPROVED | CHANGES_REQUESTED | BLOCKED
**Round:** N

## Blocking findings
- [file:line] <defect> → <concrete failure scenario>

## Non-blocking notes
- ...

## Checks run
- <command> → pass/fail
```

## Lifecycle

```
Claude: write BUILD-<feature>.md
   └─► DeepSeek builds schema/contracts      → commits to branch
   └─► MiMo builds perf-critical paths       → commits to branch
   └─► DeepSeek + MiMo cross-verify          → VERDICT files
   └─► Codex independent validation          → VERDICT file
   └─► Claude independent validation + gate  → VERDICT + SUMMARY
Gate: every required verdict APPROVED → open PR. Never push to main.
```

## Hard rules

- No agent pushes to `main`. Slices land as `slice/<feature>` branches + PR.
- No secrets in committed files. Config via env var or Databricks secrets only.
- No agent gets unrestricted SQL. Parameterized queries only.
- A builder may not approve its own work as the sole verdict.
- Tests must actually run. A verdict claiming "tests pass" without a pasted
  command and result is itself a blocking finding.
