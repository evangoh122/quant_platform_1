# BUILD-ui-A1 round 3b (DeepSeek CHANGES_REQUESTED — contrast test is vacuous)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/deepseek/VERDICT-ui-A1-r3.md`. LF endings, never touch `.agents/dispatch.sh`.
Shell rule: if a command needs quoting, write it to `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` and run exactly
`wsl -d Ubuntu -- bash /home/jianj/code/qp1-ui/.agentlogs/<name>.sh`. No .ps1/.bat files, no PowerShell wrappers, nothing in C:\temp.
COMMIT; verdict `.agents/mimo/VERDICT-ui-A1-r3b.md`.
The contrast test (frontend/src/layout/layout.test.tsx:563-582) hardcodes the colours. Read the REAL token values from the stylesheet with
Vite's raw import — `import css from '../index.css?raw'` (vite/client types are already referenced via src/vite-env.d.ts; no Node `fs`
import) — parse `--surface`, `--text-muted`, `--warning` (light and dark blocks) and assert each text token is >= 4.5:1 on its surface.
Delete the hardcoded literals and the fake "mutation" cases that test literals. Show FAILED output in the verdict with `--text-muted: #94a3b8`
and `--warning: #d97706` set in index.css (in a `git archive HEAD | tar -x -C /tmp/<dir>` copy). vitest, `tsc --noEmit` and build must pass.
