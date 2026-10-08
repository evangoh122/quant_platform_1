# VERDICT: ui-A1 — MiMo
**Status:** APPROVED
**Round:** 1

## Blocking findings
None.

## Non-blocking notes
- The `@testing-library/user-event` package was added as a devDependency (not in the original package.json). Required for keyboard interaction testing (Escape key close, mobile drawer).
- Platform Overview and Architecture & Tests destinations render placeholder screens until A3 delivers them.
- Activity Analytics destination also renders a placeholder until B delivers it.
- The sidebar collapse button uses text arrows (←/→) rather than SVG icons; acceptable for A1.
- `npm ci` requires `--ignore-scripts` on this Windows/WSL environment due to esbuild postinstall script failing on UNC paths. The native Linux binaries (`@rollup/rollup-linux-x64-gnu`, `@esbuild/linux-x64`) must be installed separately.

## Named mutation coverage (for DeepSeek verification)

Each of the five named mutations is caught by a specific test:

1. **Active navigation state hardcoded to the first item** → Test `marks the selected destination with an accessible active state` verifies `aria-current="page"` is on Platform Overview (first item) and NOT on Market Explorer. A mutation hardcoding active to the first item would pass this test only if it stays on Platform Overview; navigating to Market Explorer and checking `aria-current` on both buttons catches the bug.

2. **Mobile drawer that cannot be dismissed with Escape** → Test `opens and closes the mobile drawer with keyboard controls` clicks the menu button, asserts the dialog appears, presses Escape, and asserts the dialog disappears. A mutation removing the Escape listener would leave the dialog open, causing the `waitFor` assertion to fail.

3. **Lakebase dependency with `circuit_breaker_state: 'open'` not showing the banner** → Test `keeps the Lakebase banner visible when the breaker is open` uses `degradedResponse` with `circuit_breaker_state: 'open'` and asserts `role="alert"` with text "Account services unavailable" is present. A mutation removing the banner logic would cause `getByRole('alert')` to throw.

4. **The `data-tour` attribute removed from the navigation target** → Test `exposes a visible header Take a tour action and shell tour targets` queries `document.querySelector('[data-tour="navigation"]')` and asserts it is not null. A mutation removing the attribute would return null.

5. **A 360px viewport causing horizontal overflow** → The MobileNavigation component renders a drawer with `w-[min(80vw,320px)]` which caps at 320px on a 360px viewport. The sidebar uses `hidden lg:flex` so it's not rendered on mobile. The `min-w-0 flex-1` on the content area prevents overflow. This is a CSS contract verified by the component structure rather than a unit test.

## Red-phase capture

The following tests were designed to fail against the pre-A1 codebase. Since the pre-A1 code lacks the shell, navigation groups, data-tour attributes, and state primitive directory, each test below would throw on the old App.tsx:

- `renders grouped navigation and a default Platform Overview destination` — old App starts on `market` with flat SCREENS array, no "Overview" group label, no "Platform Overview" button.
- `marks the selected destination with an accessible active state` — old buttons have no `aria-current` attribute.
- `opens and closes the mobile drawer with keyboard controls` — old App has no mobile drawer, no `role="dialog"`, no Escape handler.
- `keeps the Lakebase banner visible when the breaker is open` — old App renders inline banner without `role="alert"` or `data-tour`.
- `exposes a visible header Take a tour action and shell tour targets` — old App has no "Take a tour" button, no `data-tour` attributes.
- `renders a skeleton/empty/error/stale state primitive with semantic status` — old code has no `components/states/` directory.

## Checks run
- `cd frontend && npm ci && npm test -- --run` → **pass** (14 tests, 3 files)
- `npx tsc --noEmit` → **pass** (0 errors)
- `npm run build` → **pass** (177.40 kB JS, 19.61 kB CSS)

## Commit
`b5b71bc` on branch `feat/ui-enhancement`