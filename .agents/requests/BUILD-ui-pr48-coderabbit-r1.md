# BUILD — PR #48 CodeRabbit repair round 1

You are MiMo. Work only on `feat/ui-enhancement` at or after PR #48 head
`4044ae62de6450e1d46109237b126041bd72367b`. Fix the verified current-head
CodeRabbit findings below. Do not add dependencies, redesign the theme, modify
V1/V5, deploy, or broaden the data plans beyond the stated contracts.

## A. Evidence safety and correctness

1. `frontend/src/components/evidence/ProvenanceGrid.tsx:4-92`
   - Validate/sanitize every SEC row field before JSX. String fields pass only
     when actually strings; numeric fields pass only when finite numbers.
   - Malformed object-valued fields must render fallbacks, never React children.

2. `frontend/src/components/evidence/SourceCard.tsx:51-60`
   - Render a source link only when defensive URL parsing yields `http:` or
     `https:`. Reject invalid, `javascript:`, `data:`, and `file:` URLs.

3. `frontend/src/components/evidence/ToolCallCard.tsx:112-127`
   - For `save_research_note`, claim Lakebase storage only when the call is
     successful and a `note_id` exists. Preserve valid behavior for other
     confirmed write tools.

Add dedicated evidence-component tests covering malformed object fields,
allowed/rejected protocols, and note-save responses with/without `note_id`.

## B. Trace, ticker, and date behavior

4. `frontend/src/components/ExecutionTrace.tsx` and
   `frontend/src/screens/ResearchAgent.tsx`
   - Use an explicit reply-delivered/response-state signal. Sending with no
     reply is pending; a delivered reply is complete even with zero tools;
     finished error with no reply is failed. Do not misuse data `available` as
     proof that a response was delivered.

5. `frontend/src/components/SymbolPicker.tsx:93-162`
   - Enter selects the highlighted option, or otherwise submits a trimmed,
     uppercased custom ticker only when it matches `TICKER_RE`.
   - Keep a ref synchronized with the latest `value` and read it inside the
     delayed blur callback so a stale prop cannot overwrite a new selection.

6. `frontend/src/screens/MarketDashboard.tsx:42-50`
   - Build the range cutoff at UTC midnight and subtract with `setUTCDate`.
   - Add a UTC+ timezone and month/year-boundary regression test.

7. `frontend/src/screens/ResearchAgent.tsx:19-21`
   - Replace every `{SYMBOL}` occurrence, not only the first. Test a template
     containing two placeholders.

## C. Guided tours

8. `frontend/src/components/tours/CoachMarks.tsx:115-127`
   - While open, cycle Tab from last focusable to first and Shift+Tab from first
     to last. Retain focus on the card if there is no focusable child. Register
     and clean up both `keydown` and `focusin` handlers.

9. `frontend/src/components/tours/TourHost.tsx:49-69`
   - Guard the unseen-tour auto-start check so it runs once per host mount.
     Closing/skipping one tour must not auto-start the next. Manual tour request
     events must remain functional.

10. `frontend/src/components/tours/tourSteps.ts:35-56` and
    `frontend/src/screens/ResearchAgent.tsx`
    - Add stable agent-local targets for note confirmation/action and evidence.
      Point `AGENT_TOUR` to those targets. Do not target Paper Portfolio or
      System Health; the runner does not navigate.

Add keyboard wrap, no-tour-chain, manual-start, and selector-resolution tests.

## D. Tests and architecture copy

11. `frontend/src/layout/layout.test.tsx:371-505`
    - Test the rendered `Options Analytics` navigation button, not a test-local
      constant.
    - Delete the self-fulfilling width mutation test. Keep one production-DOM
      scan proving no rendered fixed/min width exceeds 360px.

12. `frontend/src/screens/ArchitectureEvidence.tsx` and its tests
    - Group Massive, SEC, CFTC, and FRED into one upstream-provider node before
      Spark; do not depict sequential provider-to-provider flow.
    - Describe Lakebase note saving as optional and conditional on returned
      `note_id`, not as an unconditional outcome.

## E. Plan-contract corrections

13. `docs/data/PLAN-analytics-metrics.md`
    - Specify `max_gap_days=5` calendar days for 1-day labels; beyond it,
      label/label timestamp/realized return remain null and the signal is
      excluded from realized metrics.
    - For Agent Activity, Latency, Model Performance, and Stream Freshness,
      name the controlling timestamp, expected cadence/deadline, grace rule,
      and deterministic stale behavior. Derive cadence from the documented job;
      do not invent unsupported numeric schedules.

14. `docs/data/PLAN-massive-incremental.md`
    - Every correction version gets its own `information_available_ts`.
    - Historical features select the latest retained natural-key version with
      `information_available_ts <= prediction_ts`.
    - Use append-only Bronze replay as the history-preserving source for this
      plan; latest-only Silver is not sufficient.
    - Require the M3 original-before-prediction / correction-after-prediction
      regression fixture.

15. `docs/ui_enhancement/OWNER_PLAN.md`
    - Replace account-specific email/home paths with neutral placeholders.

16. `docs/ui_enhancement/PLAN-B-workbench-visuals-xbrl.md`
    - Enforce the SEC identity-wide cap by serializing SEC ingestion jobs:
      `max_concurrent_runs: 1` and no overlapping manual runs. Retain the 8 rps
      target, 10 rps hard maximum, jitter, bounded retries, and `Retry-After`.
    - Restrict cumulative differencing to additive duration flows. Quarterly
      EPS must use a reported discrete-quarter fact or be unavailable with a
      quality flag. Require a YTD-only EPS fixture that produces no fabricated
      quarterly EPS.

## Tests that must fail on current head

- Malformed SEC object field crashes or fails fallback assertion.
- `javascript:` source creates an anchor.
- Successful note call without `note_id` claims Lakebase storage.
- Custom valid ticker cannot submit with Enter.
- Blur timeout restores the stale symbol.
- UTC+ chart cutoff includes an extra day.
- Closing one tour starts another; Tab does not wrap; agent selectors do not
  resolve on Research Agent.
- Removing Options Analytics from production navigation does not fail the old
  local-constant test.
- Two `{SYMBOL}` placeholders leave one unreplaced.

## Required mutation proofs

Use separate fresh `git archive` copies under `/tmp`; never mutate the worktree.

1. Restore object-only SEC row checking.
2. Drop the HTTP(S) protocol allowlist.
3. Restore unconditional Lakebase storage text.
4. Restore highlighted-option-only Enter handling.
5. Read the captured blur `value` instead of the synchronized ref.
6. Restore local-midnight date arithmetic.
7. Remove the Tab wrap handler and the one-mount auto-start guard.
8. Restore a cross-screen agent-tour selector.
9. Remove Options Analytics from production `NAV_GROUPS`.
10. Split providers back into sequential nodes and restore unconditional note
    wording.
11. Replace only the first symbol placeholder.

Every mutation must make its targeted unmodified regression test fail.

## Acceptance commands

Run without `npm install` or `npm ci`:

```bash
cd frontend
npx vitest --run
npx tsc --noEmit
npm run build
cd ..
git diff --check
```

Use LF endings. Do not touch `.agents/dispatch.sh`. Stage only intended files,
commit on `feat/ui-enhancement`, and write
`.agents/mimo/VERDICT-ui-pr48-coderabbit-r1.md` containing the commit SHA,
failing-before evidence, all mutation failures, and acceptance output. Do not
push, merge, deploy, or comment on the PR. MiMo's verdict is a self-report;
Kimi and Codex must independently validate before CodeRabbit is retriggered.
