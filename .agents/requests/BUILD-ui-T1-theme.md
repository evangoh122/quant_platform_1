# BUILD-ui-T1 — adopt the Rag_workbench look (owner: "the colors are off")

You are MiMo. Branch `feat/ui-enhancement`, worktree /home/jianj/code/qp1-ui (`git branch --show-current` before each commit). Shell rule: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`
or a script in `/home/jianj/code/qp1-ui/.agentlogs/<name>.sh` via `wsl -d Ubuntu -- bash <path>`. No PowerShell wrappers, nothing in C:\temp, NEVER npm ci/install, NO new dependencies
(no @fontsource, no Google Fonts link — CSS font stacks only). LF endings, never touch `.agents/dispatch.sh`, stage only your files, commit per item.

Reference (read-only): /home/jianj/code/Rag_workbench/frontend/src/index.css and its components for look only. Do NOT copy Rag_workbench components or App.tsx; keep every qp1 behaviour, test id and API contract.

1. **Tokens** in `frontend/src/index.css`: dark theme only (`color-scheme: dark`), mapped from Rag_workbench:
   --canvas #090A0C; --surface #111317; --surface-raised #181B20; --border #32363D; --border-subtle #22262C; --text-primary #F3F1EA; --text-secondary #B8BDC5; --text-muted #818791;
   --accent #D6B65A; --accent-bright #F1D77A; --accent-fill #C9A227; --accent-ink #171205; --accent-dim rgba(214,182,90,.14); --silver #C7CBD1; --positive #43D19E;
   --negative #FF727F; --neutral #A8B0BC; keep --warning/--info but retune to read on dark (warning #E0A458, info #7FB8D6). Radii 6/8/12px. Fonts: "Geist","Segoe UI Variable",system-ui,…
   and mono "JetBrains Mono","SF Mono",ui-monospace,…. Tabular numbers on tables/values. The faint 48px grid backdrop (`body::before`) and a restrained gold scrollbar.
   Focus ring uses --accent. Check text/background contrast ≥ 4.5:1 for primary/secondary/muted text and for accent text on surface.
2. **Tailwind** (v3): expose the tokens in tailwind.config (`canvas`, `surface`, `surface-raised`, `border`, `fg`, `fg-secondary`, `fg-muted`, `accent`, `positive`, `negative`, …
   as `var(--…)` colours) and replace the ~150 hard-coded palette classes (`slate-*`, `blue-*`, `emerald-*`, `red-*`, `gray-*`, `dark:*` variants) across frontend/src with token classes.
   Status pills (ExecutionTrace, FreshnessBadge, states) map complete→positive, failed→negative, running→accent, pending/skipped→muted, using `color-mix`/dim backgrounds on dark.
3. **Charts:** every SVG fill/stroke uses `var(--…)` tokens (price line accent gold, volume silver/dim, up/down positive/negative, gridlines --border-subtle).
4. **Test** `frontend/src/theme.test.ts`: scan every `.tsx` under src (excluding tests) and fail on raw Tailwind palette classes (regex for `\b(?:bg|text|border|ring|fill|stroke|from|to)-(?:slate|gray|zinc|neutral|blue|emerald|green|red|amber|yellow|sky|indigo)-\d{2,3}\b`)
   and on hex colours in TSX. Mutation: re-add one `bg-slate-200` → fails. Plus a render test that ExecutionTrace's failed pill uses the negative token class.
Full vitest/tsc/build must pass. Verdict `.agents/mimo/VERDICT-ui-T1.md` listing replaced-class counts and the contrast ratios you computed.
