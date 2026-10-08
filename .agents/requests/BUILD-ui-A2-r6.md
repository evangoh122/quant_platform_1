# BUILD-ui-A2 round 6 (Codex round-2 CHANGES_REQUESTED)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/codex/VERDICT-ui-A2-r2.md`. LF endings, never touch `.agents/dispatch.sh`.
Run frontend commands from WSL directly: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`.
Never wrap wsl.exe in PowerShell and never write scripts to C:\temp. COMMIT and write `.agents/mimo/VERDICT-ui-A2-r6.md`.
1. CoachMarks.tsx:164 — clamp BOTH edges first: `left = clamp(raw.left, 0, vw)`, `right = clamp(raw.right, 0, vw)`, same for top/bottom; then
   `width = max(0, right - left)`, `height = max(0, bottom - top)`. A target entirely off-screen (any side) → scroll it into view or use the
   centered card, never a zero/negative spotlight. Tests: vw=1024 with rect.left=1200,width=100 → width >= 0 and spotlight inside [0, vw]
   (or centered fallback); same for a target above/below the viewport. Paste FAILED output with the old one-edge clamp restored.
2. CoachMarks.test.tsx:377 — the "360px viewport" test must actually set `window.innerWidth = 360` (and dispatch resize); keep a separate
   1024px case if useful.
