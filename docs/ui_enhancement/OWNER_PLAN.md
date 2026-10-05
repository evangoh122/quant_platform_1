# Capstone UI/UX integration plan (owner, 2026-10-05) — binding source for the UI lane

## Objective
Upgrade the current frontend into a guided, auditable research application that clearly demonstrates: external market and
SEC data; Spark/Delta processing; AI retrieval and Lakebase write actions; provenance and tool execution; Lakebase→Delta
analytics; system health and failure handling. Use selected UX ideas from Rag_workbench (local copy: /home/jianj/code/Rag_workbench;
workspace copy /Workspace/Users/evangohsg@gmail.com/Capstone/Rag_workbench). Do not replace FastAPI contracts or port the old
workbench wholesale.

## Constraints
- Preserve all currently working API routes. Keep React 18, Vite, Tailwind and the current component model.
- Do NOT import DuckDB, the old free-form SQL chatbot, LangGraph, React Flow, review-queue APIs or old backend services.
- Do NOT copy the 72 KB Rag_workbench App.tsx. Do not expose arbitrary confidence scores.
- Signals: 35 BASELINE signals are now published (model `baseline-logreg-v0-2026-10-05`, hold-out AUC 0.47, pipeline
  demonstration, no edge claimed) — label them as such; never present them as validated trading signals.
- Do not make the UI depend on unavailable analytics data. Develop on branch `feat/ui-enhancement` only.
- A company dropdown (`frontend/src/components/SymbolSelect.tsx`, lists in `frontend/src/data/symbols.json`) already exists on
  Market and Options — extend/replace it with the SymbolPicker below rather than duplicating.

## Phase 1 — Application shell and navigation
Group screens by intent: Overview (Platform Overview); Research (Market Explorer, Options Analytics, SEC Research, AI Research
Agent); Strategy (Signal Explorer, Strategy Lab); Operations (Paper Portfolio, Order Approval); Evidence (Activity Analytics,
System Health, Architecture & Tests). Rename presentation labels only; preserve internal IDs and API behaviour.
New: frontend/src/layout/{AppShell,Sidebar,MobileNavigation,PageHeader,StatusBanner}.tsx — collapsible desktop sidebar, mobile
drawer, active indicator, environment/deployment badge, global Lakebase degradation warning, visible "Take a tour" action,
keyboard-accessible navigation, responsive to 360 px. Solid surfaces, subtle borders, consistent spacing (no glassmorphism).

## Phase 2 — Guided coach marks
Adapt behaviour from Rag_workbench `frontend/src/components/CoachMarks.tsx` + `tourSteps.ts` (no disclaimer dependency, no
RAG-specific text). Tours: Application (navigation groups, market research, AI agent, Lakebase write, analytics evidence, system
provenance); Research agent (suggested question, ticker/date scope, execution progress, grounded answer, sources/provenance,
save-note action); Architecture page (external APIs, Spark bronze/silver/gold, Delta+UC, agent+Lakebase, analytics outbox,
deployed app). Requirements: versioned localStorage keys qp_tour_application_v1 / qp_tour_agent_v1 / qp_tour_architecture_v1;
replay from header; Escape/←/→; focus trap; restore focus on close; skip missing targets; no auto-start under
prefers-reduced-motion; spotlight/tooltip stay visible on resize/scroll; `data-tour` attributes (not styling classes).

## Phase 3 — Platform Overview page (default landing)
frontend/src/screens/PlatformOverview.tsx. Hero "Quant Research Platform — 287M+ market and regulatory records transformed
through Spark, searched through a governed AI agent, and audited through Lakebase and Delta analytics." Actions: ask the research
agent / explore market data / view architecture. Evidence cards (static, labelled "Verified snapshot: 2026-10-05", never as live
counters): 287M+ records; 152.1M options records; 10,720 SEC embedding chunks; 4 third-party providers; Lakebase operational
model; Spark bronze→silver→gold. Compact HTML/CSS stepper: External APIs → Spark ingestion → Delta bronze/silver/gold → AI
retrieval → Lakebase action → Delta activity analytics. Eight rubric cards linking to the relevant screen/evidence.

## Phase 4 — Research agent redesign
Replace raw JSON in ResearchAgent.tsx (keep the endpoint). Two-column layout: conversation (question, grounded answer, follow-ups,
save-note confirmation) + execution/evidence panel; evidence below the answer on mobile. Suggested questions (known to work):
"Summarize Nvidia's latest reported export-control risks." / "Find SEC evidence about Nvidia's China revenue exposure." /
"What risks does AMD describe in its latest 10-K?" / "Show recent market features for NVDA." / "Save a research note for NVDA:
export controls remain a key risk." Typed tool cards (SEC Filing Search: status, ticker, N sources, as-of; Research Note: status,
ticker, note id, storage Lakebase); raw args/results only under a collapsed "Developer details". ExecutionTrace.tsx with states
pending/running/complete/failed/skipped, deriving ONLY stages supported by the response (no simulated timing).
components/evidence/{EvidencePanel,SourceCard,ToolCallCard,ProvenanceGrid,DeveloperDetails}.tsx showing ticker, form, accession,
accepted timestamp, section, source URL, retrieval mode, tool success/failure, saved record id. No XBRL/Polygon/graph sections yet.

## Phase 5 — Analytics and system evidence
ActivityAnalytics.tsx from the existing /api/analytics contract: tool calls, retrieval vs write, success/failure, distinct users,
watchlist adds/removes, order funnel, latest refresh, source-to-target lag. Every section: loading/empty/stale/partial/unavailable/
populated. Not-yet-materialized message: "No analytics events have been materialized yet. Run the Lakebase analytics refresh to
populate this view." Never show zero as a measured result. SystemHealth.tsx: app status, SQL warehouse, Lakebase, SEC corpus,
model endpoint, circuit breaker, last success, trace id, degraded capabilities; keep stale data visible after refresh failure
(labelled stale), manual refresh, 30 s polling, recent failures, per-service cards; no internal exception text or credentials.

## Phase 6 — Architecture & Tests page
ArchitectureEvidence.tsx: business workflow (question → governed retrieval → grounded response → saved note → Lakebase audit →
Delta analytics); responsive technical diagram (Massive/SEC/CFTC/FRED → Spark → Delta bronze/silver/gold → FastAPI → React → AI
agent → Lakebase → analytics_outbox → Spark analytics → Delta analytics) — may embed docs/proposal/architecture.png; deterministic
safety model (LLM proposes → typed schema validates → allowlist → write authorisation → deterministic execution → audit record);
verified test groups with commit SHA/date (no fabricated live count); known limitations (baseline signals only, DLT built not
deployed, paper broker scaffold, analytics need the refresh run).

## Phase 7 — Market and options UX
SymbolPicker.tsx (text input + recent symbols in localStorage + quick choices NVDA/AAPL/MSFT/AMD/SPY + the existing data-backed
lists + `?symbol=` URL param + no-coverage message + coverage indicator + validation) used in Market, Options, SEC Research, Agent.
One modest chart: adjusted close + volume with range selector, table still available, empty state, source/freshness label.
Signal page: show the baseline signals with the baseline label; the empty state (if ever empty) links to Architecture & Tests.

## Phase 8 — Design system cleanup
Tokens in index.css (--canvas, --surface, --surface-raised, --border, --text-primary/secondary/muted, --accent, --positive,
--warning, --negative, --info); one accent, one radius scale, 4/8 px rhythm, tabular numerals for metrics, monospace only for ids,
visible focus rings, WCAG AA. components/states/{LoadingSkeleton,EmptyPanel,ErrorPanel,StaleDataNotice,SuccessToast}.tsx;
skeletons instead of full-page spinners.

## Phase 9 — Testing
Coach marks (auto once, no reopen, replay, next/back/skip, Escape, missing selector, versioned key, focus restore, mobile).
Agent UI (suggested question submits, answer, retrieval card, failed tool, saved-note confirmation, raw JSON collapsed, send
disabled during submit, empty input blocked, API failure keeps the question). Navigation (every destination, active state, mobile
drawer, Lakebase banner, tours navigate). Analytics (populated, empty not shown as zero, stale kept on failure, partial sections).
Accessibility (keyboard, focus-visible, dialog semantics, live regions, heading order, contrast, reduced motion).
Acceptance: cd frontend && npm ci && npm run test && npm run build && npx tsc --noEmit; backend tests for contracts used.

## Delivery slices
A (first): app shell, Platform Overview, coach marks, Research Agent redesign + evidence/tool cards, Architecture & Tests,
SymbolPicker, focused tests. B: Activity Analytics, improved System Health, Lakebase write confirmation, empty/stale states,
screenshots. C (later): richer charts, review queue, KG explorer, drift dashboard, audit-log browser, more tours.
Do not port the Rag_workbench review queue yet.
