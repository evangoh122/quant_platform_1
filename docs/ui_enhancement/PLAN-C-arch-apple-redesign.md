# PLAN-C — Architecture diagram + Apple-HIG frontend redesign

Status: draft by Opus, pending Codex Sol critique. Branch `feat/arch-apple-redesign`.
Binding constraints still come from `OWNER_PLAN.md` (React 18, Vite, Tailwind, current
component model, preserve API routes, **solid surfaces, no glassmorphism**).

## Goals
1. **Architecture diagram** — replace the static GIF/PNG on the Architecture & Tests screen with
   a native inline-SVG diagram in the Cocoon `architecture-diagram` style
   (`.agentlogs/skills/architecture-diagram/SKILL.md`): semantic colours per component type,
   arrows behind boxes, 40 px vertical gaps, legend outside boundaries.
2. **Perps pipeline** — show the planned Hyperliquid / Binance weekend-signal path
   (Bronze → Silver → Gold → MLflow comparison) in the diagram. These components are
   **PLANNED, not built**: render with dashed stroke and a "Planned" legend entry; never imply
   they exist in production. Same honesty rule as `LIMITATIONS` in `ArchitectureEvidence.tsx`.
3. **Frontend polish** — apply Apple HIG principles
   (`.agentlogs/skills/apple-design/SKILL.md`; cite `references/hig/<page>.md`): typography
   scale, spacing, colour contrast, focus and hit-target sizes, dark mode, reduced motion,
   accessible navigation. Do NOT adopt Liquid Glass / translucency (OWNER_PLAN forbids it).

## Non-goals
- No new runtime dependencies (no chart/diagram libraries, no html2canvas/jsPDF export bar).
- No API, backend, schema or route changes. No Rag_workbench imports.
- No claim of trading edge; baseline-signal labelling stays exactly as is.
- Do not remove existing test ids / strings asserted by current tests unless the test is updated
  in the same commit with a stated reason.

## Numbered changes
1. `frontend/src/components/ArchitectureDiagram.tsx` (new): inline SVG, props-free, data-driven
   from a typed `NODES` / `EDGES` const. Component types: frontend, backend, database, cloud,
   security, bus, external, planned. `role="img"`, `<title>`/`<desc>`, text alternatives.
2. `frontend/src/screens/ArchitectureEvidence.tsx`: render `ArchitectureDiagram` in place of the
   GIF/PNG; keep `PIPELINE_TECH_NODES`, `SAFETY_MODEL_STEPS`, `TEST_GROUPS`, `LIMITATIONS`
   content. Add the planned perps nodes to the diagram only (not to `PIPELINE_TECH_NODES`).
3. `frontend/src/index.css` + `frontend/tailwind.config.js`: HIG-aligned type scale and spacing
   tokens, `prefers-reduced-motion` handling, visible focus rings, 44 px minimum targets on
   touch. Keep existing class names working.
4. `frontend/src/layout/*` and shared components (`Card`, `StatTile`, `Table`, `EmptyState`,
   `ErrorState`, `LoadingState`): consistency pass only (spacing, contrast, focus, labels).
5. `frontend/src/screens/ArchitectureEvidence.test.tsx` + new
   `frontend/src/components/ArchitectureDiagram.test.tsx`: must fail on the old behaviour
   (GIF `<img>`), and assert: perps nodes are present AND marked planned, legend present,
   accessible name present, no node text overlaps (bounding-box check on NODES geometry).
6. Remove now-unused `frontend/src/assets/architecture_*.{gif,png}` ONLY if no other import
   references them (grep first); otherwise leave them.

## Acceptance commands (run from `frontend/`)
```bash
npm ci
npx tsc --noEmit
npm test            # vitest run, all pass, none skipped
npm run build
```
Plus the repo CI-parity command from AGENTS.md (with and without the pyspark stub) to prove
nothing in the Python side changed behaviour.

## Roles for this task (owner override of AGENTS.md, 2026-10-21)
- **Coder: DeepSeek** (`deepseek/deepseek-flash`) — `./.agents/dispatch.sh dsbuild ...`
- **Validator: MiMo 2.6** (`xiaomi-token-plan-sgp/mimo-v2.6-pro`) — `./.agents/dispatch.sh mimoval ...`
- **Final gates: Opus 5.5 AND Codex Sol** (both, on the same SHA, owner-requested).
- Then CodeRabbit per AGENTS.md rules.
Identification caveat: the DeepSeek API exposes only `deepseek-flash` and `deepseek-v4-pro`; the
"v4.1 flash" label could not be confirmed. The PR description must record exactly which model ID ran.
