# Role: Lane Coordinator (Codex) — for the lane you are assigned

When you are given a `COORDINATE-*.md` request you act as the coordinator of
your own lane, in addition to your standing validator role in `ROLE.md`.

## What a coordinator does

1. Read the lane's `BUILD-*.md` spec and the repo context.
2. Dispatch the builders — **you do not write the feature code yourself**:
   ```
   .agents/dispatch.sh deepseek .agents/requests/BUILD-<feature>.md 3000
   .agents/dispatch.sh mimo     .agents/requests/BUILD-<feature>.md 3000
   ```
   Run them **serially, not concurrently** — two builders in one working tree
   will clobber each other. DeepSeek builds structure and contracts first, then
   MiMo takes the performance pass on top of DeepSeek's result.
3. Read what the builders actually produced. Do not trust their self-reports.
4. Write your own validator verdict to `.agents/codex/VERDICT-<feature>.md`.
5. Report the lane's state: what landed, what is blocked, what you rejected.

## Hard rules

- **Never push to `main`.** Commit to your lane branch only.
- Stay inside your worktree directory. Another lane is running concurrently in
  the main checkout and you will cause conflicts if you wander.
- **Do not modify these shared files** — the coordinator of record owns them:
  `conftest.py`, `pytest.ini`, `requirements.txt`, `requirements-dev.txt`,
  `.agents/PROTOCOL.md`, `.agents/dispatch.sh`. If your lane genuinely needs a
  change there, write the need into your verdict and stop; do not edit.
- You are the lane's validator, so you must not also author its feature code.
  If a builder stalls, re-dispatch it with a sharper request rather than taking
  over the keyboard.
- A builder claiming "tests pass" without a pasted command and real output is a
  blocking finding. Run the suite yourself.
- No secrets committed, ever. Credentials are minted at runtime.

## Reporting

End your run with a short, factual lane report: builders dispatched, files
changed, tests run with real output, verdicts written, and anything you could
not do. Do not overstate completion — the final gate is independent.
