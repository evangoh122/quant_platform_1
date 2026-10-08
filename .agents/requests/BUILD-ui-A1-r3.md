# BUILD-ui-A1 round 3 — IMPLEMENT NOW (A2 approved by DeepSeek + Codex; Codex sol CHANGES_REQUESTED on A1)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Fix every finding in `.agents/codex/VERDICT-ui-A1.md`. Commit per item, LF endings,
never touch `.agents/dispatch.sh`, red phase + mutation FAILED output in the verdict. Frontend commands from WSL only
(`wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`); never `npm ci` from Windows.
1. MobileNavigation: no focus move on initial render (restore focus to the trigger only after a real close); `aria-modal="true"`, focus trap while open;
   tests for both.
2. Collapsed Sidebar: every nav button keeps its full accessible name (`aria-label`); test with collapsed sidebar ("Market Explorer" not "M").
3. Overflow contract: a test that fails for ANY fixed/min width wider than the viewport on shell/sidebar/header/main (scan rendered className for
   `w-[` / `min-w-[` values > 360px; containers use `min-w-0`), plus a non-vacuous table-wrapper assertion with a real table.
   Mutation: `min-w-[400px]` on the shell root → FAIL.
4. Enumerate EVERY navigation destination from `NAV_GROUPS` in a test (label renders, click navigates, id preserved). Mutation: remove
   "Options Analytics" → FAIL.
5. WCAG AA: `--text-muted` and `--warning` (as text) ≥ 4.5:1 on `--surface` (and dark-mode equivalents); contrast unit test from token values.
6. Strategy Lab destination (placeholder stating it is planned) + environment/deployment badge in the header.
Verdict: .agents/mimo/VERDICT-ui-A1-r3.md.

Run WSL commands directly as `wsl -d Ubuntu -- bash -lc '<cmd>'`. Never wrap wsl.exe in PowerShell (no ProcessStartInfo / Start-Process)
and never write scripts to C:\temp — Windows Defender blocks that pattern. Keep all A2 tests passing (62 at the start of this round).
COMMIT per item and write the verdict.
