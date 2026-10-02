# COORDINATE-REQUEST: Lane B — ml-ablation

**You are Codex, coordinating Lane B.** Read `.agents/codex/ROLE-COORDINATOR.md`
and `.agents/PROTOCOL.md` first, then this.

## Your working directory

You are in a **git worktree** dedicated to Lane B, on branch `slice/ml-ablation`.
Lane A is running concurrently in the main checkout at
`/home/jianj/code/quant_platform_1` on branch `slice/lakebase-agent-tools`.
**Stay in your worktree.** Do not cd into the main checkout, do not touch
`main`, do not edit `db/` or `agent/` — Lane A owns those files.

## Your job, in order

1. Read `.agents/requests/BUILD-ml-ablation.md`. That is the spec.

2. Dispatch **DeepSeek** to build structure, contracts and the PIT logic:
   ```
   ./.agents/dispatch.sh deepseek .agents/requests/BUILD-ml-ablation.md 3000
   ```

3. Read what DeepSeek actually produced. Check it against the acceptance
   criteria. If a builder left a stub that returns a plausible value without
   doing the work, that is a blocking finding — re-dispatch with a sharper
   request rather than fixing it yourself.

4. Then dispatch **MiMo** for the performance pass — training throughput, batch
   efficiency, inference latency budget:
   ```
   ./.agents/dispatch.sh mimo .agents/requests/BUILD-ml-ablation.md 3000
   ```
   **Serially, after DeepSeek** — never both at once in one working tree.

5. Write your validator verdict to `.agents/codex/VERDICT-ml-ablation.md`.

6. Commit to `slice/ml-ablation`. Do not open a PR — Claude holds the final gate
   and will open it after an independent validation pass.

## What matters most in this lane

The **PIT no-look-ahead test** is the thing to be hardest on. The entire
research claim is worthless if future information leaks into training rows. Do
not accept a test that only exercises the happy path; require the deliberate
leak fixture that proves the guard actually fires.

Second: confirm the ablation **actually varies the feature set between arms**. A
bug that trains identical features four times produces a clean-looking null
result and would silently invalidate the headline finding.

Third: an honest negative result is a success. If adding options/SEC/COT
features does not beat the OHLCV baseline, report that plainly. Do not let a
builder tune one arm harder to manufacture a positive result.

## Report back

Finish with a factual lane report: which builders ran, files changed, the real
test output, the A/B/C/D metrics table, your verdict, and anything you could not
complete and why. Understate rather than overstate — the gate is independent.
