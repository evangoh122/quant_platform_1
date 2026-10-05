# BUILD-ui-A2 round 5 (DeepSeek CHANGES_REQUESTED on r4 — one missing test)

You are MiMo. Branch `feat/ui-enhancement` (stay on it). Read `.agents/deepseek/VERDICT-ui-A2-r4.md`. LF endings, never touch
`.agents/dispatch.sh`. Run frontend commands from WSL directly: `wsl -d Ubuntu -- bash -lc 'cd /home/jianj/code/qp1-ui/frontend && npx vitest --run && npx tsc --noEmit && npm run build'`.
Never wrap wsl.exe in PowerShell (no ProcessStartInfo / Start-Process) and never write scripts to C:\temp — Windows Defender blocks it.
COMMIT and write the verdict.
Write the once-only test BUILD-ui-A2-r4.md item 1 asked for: render CoachMarks inside `<React.StrictMode>`; click Next until the last step,
then Done (and separately Escape); assert `onClose` was called exactly once and `markTourSeen`/localStorage.setItem for the tour key was
called exactly once; spy on console.error and assert no call contains "Cannot update a component". Paste the FAILED output with
`handleClose()` moved back inside the `setIndex` updater (`setIndex((i) => { if (i >= steps.length - 1) { handleClose(); return i; } return i + 1; })`).
Verdict `.agents/mimo/VERDICT-ui-A2-r5.md`.
