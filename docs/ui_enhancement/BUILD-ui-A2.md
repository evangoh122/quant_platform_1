# BUILD-ui-A2: coach marks and product tours

Implement only A2 from `docs/ui_enhancement/PLAN.md`, after A1 has been
committed and checked.

## Numbered changes

1. Add `frontend/src/components/tours/CoachMarks.tsx` and
   `frontend/src/components/tours/tourSteps.ts`. Adapt the useful behavior of
   `/home/jianj/code/Rag_workbench/frontend/src/components/CoachMarks.tsx` and
   `tourSteps.ts`: spotlight a matching target, center a step when its target
   is missing, recompute on resize and scroll, and provide Back, Next, Skip,
   Done, Escape, ArrowLeft, and ArrowRight behavior. Do not import the
   disclaimer dependency, RAG copy, `glass-*` styling, or any old workbench
   service.
2. Add a small `TourHost`/hook module under
   `frontend/src/components/tours/**` and wire it through the A1 shell
   handoff. Use exactly these versioned local-storage keys:
   `qp_tour_application_v1`, `qp_tour_agent_v1`, and
   `qp_tour_architecture_v1`. Auto-start once per key, mark the tour seen on
   Done or Skip, and expose replay from the header action.
3. Implement focus management: dialog semantics, focus trap while open,
   initial focus on the tour card, restore focus to the opener on close, and
   no page interaction through the overlay. Skip a missing selector by
   rendering a centered step; never leave the user blocked on a missing target.
4. Respect `prefers-reduced-motion`: do not auto-start a tour when reduced
   motion is requested, but allow explicit replay. Keep the spotlight and
   tooltip in the viewport after resize and scroll. Add `data-tour` targets
   for application navigation, market research, agent, Lakebase/write action,
   analytics evidence, provenance, and architecture pipeline nodes using
   attributes rather than CSS classes.
5. Add `frontend/src/components/tours/CoachMarks.test.tsx` and any focused
   hook tests. Tests must be deterministic: mock localStorage, matchMedia,
   ResizeObserver if used, and animation timers as needed.

## Tests that must fail on the current code

- `auto-starts only once and does not reopen after completion` — current app
  has no tour or versioned local-storage key.
- `replays from the header and supports next/back/skip` — current header has
  no replay action or tour controls.
- `closes on Escape and restores focus to the opener` — current app has no
  dialog/focus behavior.
- `traps Tab focus inside the dialog` — current app has no modal focus trap.
- `renders a centered step and continues when the selector is missing` — a
  missing-target mutation must not trap the tour.
- `does not auto-start under prefers-reduced-motion but permits explicit
  replay` — current app has no motion preference handling.
- `repositions the spotlight after scroll and resize` — current app has no
  spotlight measurement.

## Named mutations for DeepSeek

Run mutations for: changing a versioned key to an unversioned key; removing
the completion write so the tour reopens after completion; making a missing
selector block Next; removing the focus restore; making ArrowLeft wrap to the
last step; removing the reduced-motion guard; and measuring only once so the
spotlight is stale after scroll. DeepSeek must report file:line evidence.

## Acceptance

Run:

```sh
cd frontend && npm ci && npm test -- --run && npx tsc --noEmit && npm run build
```

Use LF line endings, do not touch `.agents/dispatch.sh`, commit the A2
changes, and write a MiMo verdict naming the commit and test results.
