# Build: reliable coach marks + Rag Workbench visual parity (r1)

## Objective

Implement the owner's requested UI outcome on `feat/rag-workbench-theme`:

1. Coach marks must work on a fresh application, Research Agent, Architecture,
   desktop, and mobile without depending on content that has not rendered yet.
2. The React application must use the live Rag Workbench obsidian/silver/gold
   color and component language, not the current light slate/blue presentation.

Reference source is read-only and pinned at:

`/home/jianj/code/Rag_workbench@1e6c092dd3c9e4f20c8be8f7151b854259b7c712`

The canonical palette is
`/home/jianj/code/Rag_workbench/frontend/src/index.css`, not the older
`UI_UX_FRAMEWORK.md`.

Do not deploy, start the Databricks app, write live data, add dependencies, or
change backend/API behavior. The app is intentionally stopped to avoid cost.

## 1. Coach-mark behavior

### 1.1 Cross-screen tours

- A selector-bearing step may not silently fall back to an untargeted bottom
  card merely because its screen is not mounted.
- Make tour navigation explicit. Extend the tour-step contract with the screen
  or navigation action needed for each cross-screen step, and have the host
  navigate before measuring the target.
- Wait for the requested target with a bounded observer/timeout, then either
  show the spotlight or produce a deterministic accessible skip/defer state.
  Selector-free introductory steps remain valid centered cards.
- Application-tour steps for Market, Agent, and Analytics must navigate to and
  spotlight their real targets.
- Architecture tour must navigate to/bind to the Architecture screen before
  spotlighting provenance and pipeline targets.

Likely files:

- `frontend/src/App.tsx`
- `frontend/src/components/tours/TourHost.tsx`
- `frontend/src/components/tours/CoachMarks.tsx`
- `frontend/src/components/tours/tourSteps.ts`
- relevant screen/layout files providing stable `data-tour` anchors

### 1.2 Fresh Agent tour

- The Agent tour must start on a fresh Agent screen with no messages, tool
  calls, or saved note.
- Do not require the dynamic post-success `lakebase-write` node. Add or reuse
  stable, truthful anchors for the input/actions capability and evidence area.
- Do not fabricate evidence or claim that a write occurred.

### 1.3 Manual and mobile use

- `Take a tour` must launch the route-appropriate tour: Agent on the Agent
  screen, Architecture on the Architecture screen, otherwise Application.
- Add stable mobile tour anchors to the visible menu trigger/drawer.
- At 375 px, the coach card stays inside the viewport, touch controls are at
  least 44x44 px, and the navigation and tour focus traps do not fight.
- Implement the existing `placement: top | bottom | auto` contract, including
  card-height-aware collision handling. Do not leave a public ignored option.
- Progress indicators need accessible step labels/current-step semantics.
- Bump persistence keys to a new version so the repaired onboarding is shown
  once after release; preserve manual replay regardless of seen state.
- Preserve reduced-motion behavior for automatic animation while keeping the
  explicit manual tour available.

## 2. Rag Workbench visual parity

### 2.1 Semantic token source of truth

Replace QP1's current light palette in `frontend/src/index.css` with the live
Rag Workbench dark-only palette and compatible QP1 aliases:

- background/canvas `#090A0C`
- surface `#111317`
- elevated surface `#181B20`
- primary text `#F3F1EA`
- secondary text `#B8BDC5`
- muted text `#818791`
- border `#32363D`
- subtle border `#22262C`
- accent `#D6B65A`
- bright accent `#F1D77A`
- CTA fill `#C9A227`, hover `#DEBA3E`, ink `#171205`
- accent wash `rgba(214, 182, 90, 0.14)`
- bullish `#43D19E`, bearish `#FF727F`, neutral `#A8B0BC`

Use `color-scheme: dark`, Rag's font stacks, restrained 12/8/6 px radii,
subtle 48 px background grid, gold scrollbar/selection/focus treatment, and
the existing reduced-motion/mobile accessibility rules.

### 2.2 Shared components first

Migrate reusable primitives away from `bg-white`, Slate/Blue light surfaces,
and split `dark:` branches to semantic tokens/classes. At minimum audit and
correct:

- `Card`, `StatTile`, `Table`, `EmptyState`, `ErrorState`, `LoadingState`
- `SymbolPicker` / symbol controls
- shared state primitives and evidence cards/panels
- buttons, inputs, pills/badges, table headers/rows, disabled states

Then sweep every rendered frontend screen so no primary surface/action is left
in the old light slate/blue language. Semantic warning/error/success colors may
remain distinct but must fit the dark palette and meet readable contrast.

### 2.3 Shell and navigation

- Match Rag Workbench's solid dark sidebar/header/surfaces and 12 px cards.
- Desktop and mobile active navigation use accent wash, gold label/border, and
  a left indicator rather than a solid blue block.
- Preserve collapsed sidebar behavior, `aria-current="page"`, mobile drawer,
  focus restoration, navigation enumeration, and 44 px mobile targets.
- Primary CTAs use gold fill with dark ink; secondary controls use elevated
  surfaces and borders.
- Chart lines, axes, grids, legends, empty states, and range controls use the
  same semantic palette. Do not imply missing values are zero.

## 3. Tests that must fail before the fix

Add rendered/integration coverage for:

1. Application tour advances across Overview → Market → Agent → Analytics and
   every selector-bearing step has a visible non-zero target.
2. Fresh Agent screen starts its tour without a saved note/tool response and
   without manufacturing a `lakebase-write` node.
3. Architecture tour requested elsewhere navigates before provenance/pipeline
   spotlighting.
4. 375 px navigation step targets the visible mobile control/drawer; card is
   inside the viewport and controls meet 44 px.
5. `top`, `bottom`, and `auto` placement behave as declared.
6. Missing required targets use the explicit bounded policy rather than a
   silent centered fallback.
7. Manual route-aware replay works even when the relevant seen key is `1`.
8. Theme contract asserts all canonical palette values above.
9. Desktop and mobile active navigation retain `aria-current="page"` and the
   accent-wash/indicator treatment, not a solid fill.
10. Shared primitives contain no old `bg-white`, Blue CTA, or Slate surface
    classes and render through semantic tokens.

Do not copy production logic into tests. Use rendered behavior and computed
DOM/class/token assertions.

## 4. Required mutation proofs

In isolated `git archive` copies of the pre-change and final commits:

- MUT1: remove cross-screen navigation from an Application step; its rendered
  integration test must fail.
- MUT2: restore Agent dependence on `[data-tour="lakebase-write"]`; the fresh
  Agent test must fail without waiting ten seconds.
- MUT3: restore `--canvas: #f8fafc` or `--accent: #2563eb`; the theme contract
  must fail.
- MUT4: restore solid-accent active navigation; desktop and mobile navigation
  tests must fail.
- MUT5: restore an old light surface class in one shared primitive; the
  semantic-component contract must fail.

Record exact mutation, command, exit code, and intended failing assertion.

## 5. Acceptance

Run from native WSL/Linux directly. Never invoke nested `wsl.exe`, Windows
Node/npm/npx, UNC paths, PowerShell wrappers, or inline cross-boundary commands.

```bash
cd /home/jianj/code/qp1-rag-theme/frontend
npx vitest --run
npx tsc --noEmit
npm run build
cd ..
git diff --check origin/main...HEAD
```

Also inspect the built CSS/JS bundle for the canonical palette and tour keys.
All files must be LF. Do not run `npm install` or change dependencies.

## 6. Scope and completion

- Frontend and its tests only, plus this request/verdict artifact.
- Preserve existing API contracts and screen behavior.
- Commit all intended changes on `feat/rag-workbench-theme`.
- Leave no unexpected/untracked files or helper scripts.
- Write `.agents/mimo/VERDICT-coachmarks-rag-theme-r1.md` with files, commit,
  tests, failing-before evidence, all five mutations, and scope audit.
- Finish with exactly:

`BUILD DONE | status: <SUCCESS|FAILURE> | sha: <40-char SHA or NO_COMMIT> | branch: feat/rag-workbench-theme | evidence: .agents/mimo/VERDICT-coachmarks-rag-theme-r1.md`

MiMo's report is a builder self-report. DeepSeek independent validation and
Codex final validation are still required before push/PR.
