// Business Case content (Overview, Data, Features, Controls).
// Static snapshot measured 2026-10-06; platform figures are copied from docs/BUSINESS_CASE.md.
// Study years in NEXT_APPROACH are copied from docs/QUANT_STRATEGIES.md; no strategy-result figure is quoted.
// Edited final v2: earlier interfaces and constants are unchanged; NextApproach and NEXT_APPROACH are added.
// No imports, no JSX.

export interface Snapshot {
  asOf: string;
  asOfLabel: string;
  notLiveNote: string;
}

export interface ExecutiveSummary {
  heading: string;
  situation: string;
  complication: string;
  question: string;
  answer: string;
}

export type EvidencePage = 'data' | 'features' | 'controls';

export interface KeyLine {
  governingThought: string;
  orderingLogic: string;
  arguments: { id: EvidencePage; claim: string; proof: string; page: EvidencePage }[];
}

export interface Overview {
  eyebrow: string;
  title: string;
  governingThought: string;
  users: { heading: string; items: { who: string; need: string }[] };
  whatItDoes: { heading: string; steps: { title: string; text: string }[] };
  whyThisArchitecture: { heading: string; reasons: { title: string; text: string }[] };
  notClaimed: { heading: string; intro: string; items: string[] };
}

export interface DataPage {
  eyebrow: string;
  title: string;
  governingThought: string;
  tiles: { label: string; value: string; note?: string }[];
  groups: {
    id: string;
    heading: string;
    conclusion: string;
    rows: {
      name: string;
      what: string;
      size?: string;
      status: 'loaded' | 'partial' | 'planned';
      note?: string;
    }[];
  }[];
}

export interface FeaturesPage {
  eyebrow: string;
  title: string;
  governingThought: string;
  available: { id: string; heading: string; text: string; evidence: string }[];
  planned: {
    id: string;
    heading: string;
    text: string;
    status: 'planned' | 'built-not-deployed' | 'blocked-on-owner';
    why: string;
  }[];
}

export interface ControlsPage {
  eyebrow: string;
  title: string;
  governingThought: string;
  groups: {
    id: string;
    heading: string;
    conclusion: string;
    items: { control: string; how: string; enforcedIn: string }[];
  }[];
  limitations: { heading: string; intro: string; items: { limit: string; impact: string }[] };
}

export type RoadmapStatus = 'not-started' | 'partly-built';

export interface NextApproach {
  eyebrow: string;
  title: string;
  governingThought: string;
  statusLabel: string;
  statusNote: string;
  insteadOf: { from: string; to: string };
  whatExistsToday: {
    heading: string;
    intro: string;
    items: { title: string; text: string; evidence: string }[];
  };
  whatWeIntendToDo: {
    heading: string;
    intro: string;
    orderingLogic: string;
    steps: {
      id: string;
      order: number;
      title: string;
      text: string;
      whyItMatters: string;
      proposedArtifact: string;
      acceptance: string;
      dependsOn: string[];
      status: RoadmapStatus;
      existsToday: string;
      stillToDo: string;
      evidence: string;
    }[];
  };
  studies: {
    heading: string;
    intro: string;
    items: { name: string; usedFor: string; inCodeToday: string; citedIn: string }[];
  };
  howWeWillJudgeIt: { heading: string; intro: string; items: string[] };
  honestOutlook: { heading: string; text: string };
}

export interface NavigationLinks {
  overview: string;
  data: string;
  features: string;
  controls: string;
}

// ── Snapshot banner ──────────────────────────────────────────────────────────

export const SNAPSHOT: Snapshot = {
  asOf: '2026-10-06',
  asOfLabel: 'Static snapshot measured 2026-10-06 ~09:30 SGT',
  notLiveNote:
    'These pages describe code and a dated measurement, not live data or a running service. Market data was last ingested around 2026-09-02; scheduled incremental ingestion is planned, not operating.',
};

// ── Executive summary (SCQA) ─────────────────────────────────────────────────

export const EXECUTIVE_SUMMARY: ExecutiveSummary = {
  heading: 'A governed platform turns fragmented equity data into traceable, point-in-time research.',
  situation:
    'Equity research draws on price and options feeds, regulatory filings, macroeconomic series and the researcher’s own notes. Research teams now also ask AI assistants to read and summarise that material.',
  complication:
    'These sources sit in separate systems with different timestamps, so joining them by hand is slow and a backtest or AI answer can silently use information that was not yet public. An assistant that hides its evidence, or obeys instructions planted in retrieved text, adds a harder-to-detect risk.',
  question:
    'How can a research team combine these sources at scale while proving what was knowable when, and keeping every AI-initiated action controlled and auditable?',
  answer:
    'Quant Platform is a Databricks-native research platform that lands every source in one governed lakehouse, tags data with the time it became available, and lets an AI agent change state only through deterministic, audited gates. The snapshot shows real inputs at scale, a workflow built end to end, and controls enforced in code; no validated trading edge is claimed, and the intended trading strategy is not yet built.',
};

// ── Key line: three MECE arguments in process order ─────────────────────────

export const KEY_LINE: KeyLine = {
  governingThought:
    'The answer rests on separate claims, each proved on its own page: the inputs are real, the workflow is built, and the controls are enforced.',
  orderingLogic:
    'Process order, following the data: what goes in (Data), what the platform does with it (Features), and why its output can be trusted and where it cannot (Controls).',
  arguments: [
    {
      id: 'data',
      claim: 'The platform holds real market, options and filing data at research scale.',
      proof:
        '48 tables, including 152,104,694 daily option rows, 23,420,557 minute bars and 133,886 SEC chunks with embeddings, measured on 2026-10-06.',
      page: 'data',
    },
    {
      id: 'features',
      claim: 'The workflow is built end to end; the intended strategy is not yet built.',
      proof:
        'Ingestion, cleaning, features, retrieval, the agent, baseline signals and audit exist in code; scheduled ingestion, streaming deployment, placeholder screens and the intended ranking strategy do not, and a research roadmap names what is still to do.',
      page: 'features',
    },
    {
      id: 'controls',
      claim: 'Point-in-time, agent and engineering controls are enforced in code, with their limits stated.',
      proof:
        'Agent writes pass a typed schema, an allowlist, request-scoped authorisation and a role check before deterministic execution and an audit record; known limitations are listed alongside.',
      page: 'controls',
    },
  ],
};

// ── Page 1: Overview ─────────────────────────────────────────────────────────

export const OVERVIEW: Overview = {
  eyebrow: 'Business case · Overview',
  title: 'Quant Platform delivers governed, point-in-time equity research without claiming a trading edge.',
  governingThought:
    'Quant Platform is an end-to-end research workflow, from raw data to audited action, whose value lies in traceability and control rather than in proven returns.',
  users: {
    heading: 'Every target user needs the same thing: evidence they can trace and trust.',
    items: [
      {
        who: 'Quantitative researchers',
        need: 'Build features and fit models without look-ahead, using data tagged with the time it became available.',
      },
      {
        who: 'Equity analysts',
        need: 'Read filing sections and receive AI answers backed by retrieved SEC passages they can inspect.',
      },
      {
        who: 'Small quantitative teams',
        need: 'Share watchlists, research notes and paper orders in one governed surface instead of scattered notebooks.',
      },
      {
        who: 'Research and risk leads',
        need: 'Trace each agent write and paper order to an authorised user, a recorded approval and an audit row.',
      },
    ],
  },
  whatItDoes: {
    heading: 'Each stage hands governed data to the next, from raw source to audited action.',
    steps: [
      {
        title: 'Ingest raw sources into bronze.',
        text: 'Batch jobs land equities, options, SEC filings, CFTC positioning and Federal Reserve series in bronze Delta tables, preserving source lineage.',
      },
      {
        title: 'Clean and quarantine in silver.',
        text: 'Silver transforms type, deduplicate and validate records; malformed market bars go to a quarantine table instead of the clean layer.',
      },
      {
        title: 'Build time-tagged features in gold.',
        text: 'Gold tables hold research features, the tradable universe, SEC embeddings and model inputs, each tied to the time its information became available.',
      },
      {
        title: 'Research with cited evidence.',
        text: 'React screens and FastAPI routes serve market, options, filing and signal views; the agent retrieves only SEC passages accepted by the as-of time.',
      },
      {
        title: 'Act only through gates.',
        text: 'The agent can save a research note or add a watchlist symbol only after deterministic checks; paper orders require a recorded human approval.',
      },
      {
        title: 'Record and analyse every change.',
        text: 'Changes to notes, watchlists, orders, approvals and agent actions write an outbox event in the same transaction; an on-demand job merges them into Delta.',
      },
    ],
  },
  whyThisArchitecture: {
    heading: 'Each layer has a distinct job, which keeps the whole system inspectable.',
    reasons: [
      {
        title: 'Medallion layers separate lineage, cleaning and consumption.',
        text: 'Bronze keeps raw inputs, silver applies cleaning and quarantine rules, and gold serves consumption-ready features, so each layer can be inspected and rebuilt on its own.',
      },
      {
        title: 'Lakebase holds the transactional state Delta is not built for.',
        text: 'Postgres stores watchlists, notes, orders, executions, positions and agent actions with transactional consistency that analytical fact tables do not provide.',
      },
      {
        title: 'A transactional outbox links the two without dual writes.',
        text: 'Each operational write and its outbox event commit together; an idempotent Delta merge then turns those events into activity analytics.',
      },
      {
        title: 'Deterministic code, not the model, holds authority to act.',
        text: 'The language model only proposes typed actions; the runtime validates them and executes through a closed registry, so model output alone never changes state.',
      },
    ],
  },
  notClaimed: {
    heading: 'The case claims a governed platform, not a strategy, profits, live operation or customers.',
    intro:
      'These boundaries are part of the answer. They are stated up front so the evidence on the following pages is read at its true weight.',
    items: [
      'No validated trading edge and no implemented strategy: the 35 baseline signals come from an untuned one-trading-day logistic regression that proves the pipeline; the intended ranking strategy on the Features page is not yet built.',
      'No live data: every figure is a snapshot measured on 2026-10-06, and market data was last ingested around 2026-09-02.',
      'No running service: these pages describe code and a dated measurement, not a deployed or monitored application.',
      'No live trading: the IBKR integration is a paper-broker scaffold, and no order reaches a real market.',
      'No universal point-in-time guarantee: controls apply at named boundaries, and revised macro series and split-adjusted price levels fall outside them.',
      'No customers, revenue, benchmarks or certifications: the users described are intended roles, not adopters.',
      'No investment advice: strategy reports in the repository are descriptive research, not recommendations.',
    ],
  },
};

// ── Page 2: Data (key-line argument 1) ──────────────────────────────────────

export const DATA: DataPage = {
  eyebrow: 'Business case · Data',
  title: 'The platform holds real data at research scale, with freshness and coverage gaps stated.',
  governingThought:
    'A dated inventory of 48 tables shows the inputs are real and sized, and shows equally plainly where data is stale, partial or still planned.',
  tiles: [
    { label: 'Tables', value: '48', note: 'Unity Catalog count at the snapshot.' },
    { label: 'Daily option rows', value: '152,104,694' },
    { label: 'Minute bars', value: '23,420,557' },
    { label: 'SEC chunks and embeddings', value: '133,886', note: 'Every chunk has an embedding.' },
    { label: 'Tradable-universe symbols', value: '557' },
    { label: 'Model snapshots', value: '40,983' },
    { label: 'Baseline signals', value: '35', note: 'Pipeline demonstration, not a trading edge.' },
  ],
  groups: [
    {
      id: 'market-options',
      heading: 'Market and options history is deep but was last ingested around 2026-09-02.',
      conclusion:
        'Equity and options history is the largest input, but it stops at the last ingest and has no scheduled refresh.',
      rows: [
        {
          name: 'Massive/Polygon equities',
          what: 'Minute bars, OHLCV features and the tradable universe.',
          size: '23,420,557 minute bars; 23,377,478 feature rows; 281,700 universe rows covering 557 symbols',
          status: 'loaded',
          note: 'Gold features carry an availability timestamp; split-adjusted price levels are current-scale and approved for returns only.',
        },
        {
          name: 'Massive/Polygon options',
          what: 'Daily per-contract option history feeding gold volume features.',
          size: '152,104,694 daily option rows; 60,068 silver trade rows; 20,318 gold feature rows',
          status: 'partial',
          note: 'Volume features read bronze_options_day directly; implied volatility, open interest and delta exposure come only from a quote snapshot.',
        },
      ],
    },
    {
      id: 'filings-context',
      heading: 'Filings and external data broaden research, but their coverage is partial.',
      conclusion:
        'SEC text is embedded at scale; fundamentals remain a five-ticker pilot, and macro history is revised rather than vintage.',
      rows: [
        {
          name: 'SEC EDGAR text',
          what: '10-K and 10-Q sections since 2024-09, embedded with BAAI/bge-small-en-v1.5, plus coverage records and extracted entities.',
          size: '191,248 bronze rows (225 tickers / 2,845 filings); 133,886 chunks and embeddings across 229 tickers; 90,456 entities',
          status: 'partial',
          note: 'The coverage table lists 558 tickers, 230 with chunks; retrieval admits only filings accepted by the as-of time.',
        },
        {
          name: 'SEC XBRL fundamentals',
          what: 'Pilot of reported financial facts for NVDA, AAPL, MSFT, AMD and XOM.',
          size: '129,822 facts; 59,610 acceptance-time-resolved; 70,212 quarantined',
          status: 'partial',
          note: 'Historical pilot measurement, not re-measured at the snapshot. Quarantined facts fall outside the 2024-09+ filing window; bronze/silver work is not fully merged.',
        },
        {
          name: 'Gold quarterly fundamentals',
          what: 'Quarterly fundamentals derived from resolved XBRL facts.',
          status: 'planned',
          note: 'Not yet built.',
        },
        {
          name: 'CFTC COT',
          what: 'Futures positioning reports turned into gold COT features.',
          size: '1,464 gold feature rows',
          status: 'loaded',
          note: 'Keyed to report date and publication availability; no separate latest-source timestamp is reported.',
        },
        {
          name: 'Federal Reserve / FRED',
          what: 'Rates and macroeconomic series in bronze tables.',
          status: 'partial',
          note: 'Row counts were not measured. Revised series use ingest time as availability and are not first-release vintage data.',
        },
      ],
    },
    {
      id: 'model-operations',
      heading: 'Model and operational data link research outputs to an auditable record.',
      conclusion:
        'Model inputs and signals are measured; operational and analytics tables exist, but their row counts were not measured.',
      rows: [
        {
          name: 'Model and signals',
          what: 'Daily symbol snapshots feeding a one-trading-day logistic-regression baseline.',
          size: '40,983 daily symbol snapshots; 35 published signals',
          status: 'loaded',
          note: 'Signals demonstrate the pipeline, not a trading edge.',
        },
        {
          name: 'Lakebase operations',
          what: 'Users, watchlists, research notes, orders, executions, positions, approvals, agent actions and the analytics outbox.',
          status: 'partial',
          note: 'Schema defined in versioned migrations; row counts were not measured for this snapshot.',
        },
        {
          name: 'Delta analytics',
          what: 'Change events plus agent-activity, watchlist, order-funnel and daily-usage tables.',
          status: 'loaded',
          note: 'Populated at measurement, counts not measured. Refresh is an on-demand job, not a schedule.',
        },
      ],
    },
  ],
};

// ── Page 3: Features (key-line argument 2) ──────────────────────────────────

export const FEATURES: FeaturesPage = {
  eyebrow: 'Business case · Features',
  title: 'The workflow is built end to end; the intended strategy is not yet built.',
  governingThought:
    'Every stage from ingestion to audited action exists in code today. The baseline model proves that workflow and is not the strategy. Planned, undeployed and placeholder items are listed below, followed by the research roadmap for the strategy, which is not yet built.',
  available: [
    {
      id: 'medallion',
      heading: 'Batch pipelines turn raw sources into governed research tables.',
      text: 'Silver and gold SQL, run by an orchestrator, clean, deduplicate, quarantine and time-tag data before any screen or model reads it.',
      evidence: 'pipelines/run_silver_gold.py; silver/; gold/',
    },
    {
      id: 'market',
      heading: 'The Market Dashboard charts split-adjusted daily bars for each symbol.',
      text: 'The screen reads daily bars through a parameterised market API; the same data adapter also serves intraday gold features for a requested window.',
      evidence: 'frontend/src/screens/MarketDashboard.tsx; api/routes/market.py; db/delta_adapter.py:388-432',
    },
    {
      id: 'options',
      heading: 'Options Analytics separates full volume history from snapshot-only greeks.',
      text: 'Put/call volume, ratio and a rolling volume z-score span the full history; implied volatility and exposure fields are populated only for the snapshot date.',
      evidence: 'frontend/src/screens/OptionsAnalytics.tsx; gold/02_gold_options_features.sql:1-24',
    },
    {
      id: 'sec',
      heading: 'The SEC Filing Explorer limits browsing to covered equities.',
      text: 'Analysts choose from tickers with filing coverage and read extracted sections alongside their source filings.',
      evidence: 'frontend/src/screens/SecFilingExplorer.tsx; gold/07_gold_sec_coverage.sql',
    },
    {
      id: 'retrieval',
      heading: 'Hybrid retrieval returns only filings that were public at the as-of time.',
      text: 'BM25 and vector results are fused by reciprocal rank; chunks accepted after the cutoff, or lacking a timestamp, are excluded before scoring.',
      evidence: 'api/services/hybrid_retriever.py:15-20,858-870; agent/tools_retrieval.py:127-168',
    },
    {
      id: 'agent',
      heading: 'The AI Research Agent answers in prose and shows every tool call.',
      text: 'The agent retrieves market, options, signal and SEC evidence, displays each tool call with its result, and can save a research note or add a watchlist symbol.',
      evidence: 'frontend/src/screens/ResearchAgent.tsx; agent/runtime.py; agent/contracts.py:203-224',
    },
    {
      id: 'signals',
      heading: 'Signal Explorer shows 35 baseline signals as a pipeline demonstration.',
      text: 'An untuned one-trading-day logistic regression scores gold model features and publishes to gold_trading_signals; no trading edge is claimed.',
      evidence: 'frontend/src/screens/SignalExplorer.tsx; ml/train.py; scripts/publish_baseline_signals.py',
    },
    {
      id: 'paper',
      heading: 'Paper orders require a recorded human approval before placement.',
      text: 'Order Approval and Paper Portfolio screens sit on placement logic that rereads approval, buying power and order state; the broker bridge is a paper scaffold.',
      evidence: 'frontend/src/screens/OrderApprovalDrawer.tsx; frontend/src/screens/PaperPortfolio.tsx; agent/tools_write.py:513-694; execution/bridge.py',
    },
    {
      id: 'operations',
      heading: 'Lakebase keeps research and paper-workflow state transactional.',
      text: 'Versioned migrations define users, watchlists, notes, orders, approvals, accounts, executions, positions and agent actions, with idempotency keys on notes and orders.',
      evidence: 'db/migrations/001_operational_schema.sql; db/migrations/002_approvals_accounts.sql; db/migrations/005_agent_runtime.sql',
    },
    {
      id: 'analytics',
      heading: 'An outbox pipeline turns operational changes into Delta analytics.',
      text: 'An on-demand job merges outbox events into lakebase_change_events and rebuilds agent-activity, watchlist, order-funnel and daily-usage tables.',
      evidence: 'pipelines/lakebase_analytics.py:1-12; db/migrations/004_analytics_outbox.sql',
    },
    {
      id: 'health',
      heading: 'System Health reports dependency and startup status.',
      text: 'Health endpoints probe Lakebase and the Delta warehouse under timeouts and expose startup stages to the System Health screen.',
      evidence: 'frontend/src/screens/SystemHealth.tsx; api/routes/health.py',
    },
  ],
  planned: [
    {
      id: 'incremental',
      heading: 'Scheduled incremental market ingestion is planned, not operating.',
      text: 'Market data was last ingested around 2026-09-02. A refresh design exists in docs/BRONZE_REFRESH_PLAN.md; no schedule is active.',
      status: 'planned',
      why: 'Until it runs, market features and signals age from the last ingest.',
    },
    {
      id: 'streaming',
      heading: 'Streaming DLT is built and locally validated, but not deployed.',
      text: 'A continuous bronze-silver-gold OHLCV pipeline is defined as a separate bundle that writes only dlt_-prefixed tables.',
      status: 'built-not-deployed',
      why: 'Starting it creates billable workspace resources, so it has not been run.',
    },
    {
      id: 'xbrl-gold',
      heading: 'Gold quarterly XBRL fundamentals are planned.',
      text: 'Quarterly fundamentals from resolved XBRL facts are not yet built, and the five-ticker pilot bronze/silver work is not fully merged.',
      status: 'planned',
      why: 'Fundamentals research stays limited to the pilot until both are complete.',
    },
    {
      id: 'xbrl-ui',
      heading: 'XBRL visuals are planned as part of Plan B.',
      text: 'Charts of reported fundamentals are planned on top of the XBRL tables.',
      status: 'planned',
      why: 'No XBRL screen exists in the application today.',
    },
    {
      id: 'kg-ui',
      heading: 'Knowledge-graph presentation is planned; graph-build code already exists.',
      text: 'The repository contains SEC knowledge-graph build code; the user-facing presentation is not built.',
      status: 'planned',
      why: 'Graph data alone does not give analysts a usable view.',
    },
    {
      id: 'analytics-ui',
      heading: 'The Activity Analytics screen is still a placeholder.',
      text: 'The navigation entry exists and the Delta analytics tables are populated, but the screen renders a placeholder.',
      status: 'planned',
      why: 'Activity data is queryable in Delta, not yet in the application.',
    },
    {
      id: 'strategy-lab',
      heading: 'The Strategy Lab screen is still a placeholder.',
      text: 'Strategy reports exist as descriptive research files in the repository; the in-app Strategy Lab renders a placeholder.',
      status: 'planned',
      why: 'Strategy research is readable in the repository, not yet in the application.',
    },
    {
      id: 'analytics-schedule',
      heading: 'Scheduled analytics and expanded metrics are planned.',
      text: 'The outbox-to-Delta job runs on demand today; scheduled runs and additional metrics are planned.',
      status: 'planned',
      why: 'Analytics reflect the last manual run, not a continuous feed.',
    },
    {
      id: 'next-approach',
      heading: 'The intended ranking strategy is not yet built; a research roadmap sets it out.',
      text: 'The research roadmap below states what exists today, what is still to do in dependency order, the studies it draws on, and how results would be judged.',
      status: 'planned',
      why: 'The baseline proves the pipeline, not an edge; no strategy beyond research baselines is implemented.',
    },
  ],
};

// ── Page 4: Controls (key-line argument 3) ──────────────────────────────────

export const CONTROLS: ControlsPage = {
  eyebrow: 'Business case · Controls',
  title: 'Controls enforced in code make outputs traceable; stated limits mark where trust stops.',
  governingThought:
    'Trust rests on checks the code enforces, not on model behaviour: data is time-gated, agent writes are gated, records are transactional, and CI checks each change. The limitations below bound that trust.',
  groups: [
    {
      id: 'data-pit',
      heading: 'Data is cleaned and time-gated before any model or answer uses it.',
      conclusion:
        'Point-in-time rules sit at each boundary where future information could leak: SEC retrieval, model features and training labels.',
      items: [
        {
          control: 'Malformed bars are quarantined.',
          how: 'Silver admits only bars with non-null prices, consistent high/low ranges and non-negative volume; violating rows go to a quarantine table.',
          enforcedIn: 'silver/01_silver_ohlcv.sql:67-71; silver/02_silver_ohlcv_quarantine.sql:1-10',
        },
        {
          control: 'Option rights are normalised before aggregation.',
          how: 'Case variants of put and call are matched explicitly, so mixed-case source values cannot drop volume from the totals.',
          enforcedIn: 'gold/02_gold_options_features.sql:73-74; tests/gold/test_options_right_case.py',
        },
        {
          control: 'SEC retrieval respects acceptance time.',
          how: 'Only chunks accepted by the as-of time are eligible; missing or unparseable timestamps are excluded, and tests fail if a future chunk leaks.',
          enforcedIn: 'api/services/hybrid_retriever.py:858-870; tests/rag/test_hybrid_retriever.py:3065-3100,3253-3262',
        },
        {
          control: 'Model features join as of their availability time.',
          how: 'Each market, options, SEC and COT feature joins a prediction snapshot only once its availability timestamp has passed; a leakage test fails on a leaking row.',
          enforcedIn: 'gold/05_gold_model_features.sql:1-23; gold/pit_guard.py; tests/gold/test_pit_leakage.py',
        },
        {
          control: 'Training labels respect chronology.',
          how: 'Validation uses a purged chronological split; the final refit admits only labels observed by the earliest scoring snapshot, and named mutation tests fail if this is weakened.',
          enforcedIn: 'ml/baseline_labels.py:235-285; ml/train.py; tests/ml/test_baseline_labels.py:569-628',
        },
      ],
    },
    {
      id: 'agent',
      heading: 'The model proposes; deterministic code decides whether any agent write executes.',
      conclusion:
        'Every agent write must pass a typed schema, a tool allowlist, request-scoped authorisation and a role check before deterministic execution, and each executed write leaves an audit row.',
      items: [
        {
          control: 'Typed schema and tool allowlist.',
          how: 'Model output must validate against a closed set of action types; only research-note and watchlist writes exist, and order, approval and cancellation tools are never exposed.',
          enforcedIn: 'agent/contracts.py:1-12,203-224',
        },
        {
          control: 'Budgets and action ordering.',
          how: 'Model calls and tool steps are capped per request, and a write can never be the first action: research must precede it.',
          enforcedIn: 'agent/runtime.py:43-44,360-372,473-500',
        },
        {
          control: 'Symbol and evidence binding.',
          how: 'A write must target a symbol already researched in the same trace, and a note that cites evidence must cite chunk IDs retrieved in that trace.',
          enforcedIn: 'agent/runtime.py:502-536',
        },
        {
          control: 'Request-scoped authorisation and role.',
          how: 'The request must authorise that exact write tool with an idempotency key, the user must hold the trader role, and public-demo mode refuses every write.',
          enforcedIn: 'api/schemas.py:131-143; agent/runtime.py:538-598',
        },
        {
          control: 'Untrusted evidence and fail-closed parsing.',
          how: 'Filing text sits in a delimited section marked as containing no instructions; invalid output gets one corrective retry, then the run stops without executing a tool.',
          enforcedIn: 'agent/runtime.py:161-191,418-447; tests/agent/test_runtime.py:722-760',
        },
        {
          control: 'Audited execution.',
          how: 'Validated writes run through a closed registry, and each executed write inserts an agent_actions row in the same database transaction as the change.',
          enforcedIn: 'agent/runtime.py:600-625; agent/tools_write.py:171-210',
        },
      ],
    },
    {
      id: 'access-records',
      heading: 'Identity checks and transactional records protect operational state.',
      conclusion:
        'Requests resolve to a trusted identity, reads are parameterised, and each covered change is recorded atomically for later audit.',
      items: [
        {
          control: 'Trusted identity on user routes.',
          how: 'Routes resolve the user from the trusted Databricks proxy header and reject requests without it, except in explicit development or read-only demo mode.',
          enforcedIn: 'api/deps.py:260-300',
        },
        {
          control: 'Read-only public-demo mode.',
          how: 'Demo mode serves anonymous viewers, disables write tools and refuses to start when configuration contains secret-bearing values.',
          enforcedIn: 'api/demo.py:1-10,138-160; agent/tools_write.py:79; tests/api/test_public_demo_security.py',
        },
        {
          control: 'Parameterised, bounded reads.',
          how: 'Warehouse reads bind user input as named parameters and run under a row limit and a statement timeout.',
          enforcedIn: 'db/delta_adapter.py:190-221',
        },
        {
          control: 'Transactional outbox.',
          how: 'Triggers on watchlists, notes, orders, executions, positions, approvals, signals and agent actions write an outbox event in the same transaction as the change.',
          enforcedIn: 'db/migrations/004_analytics_outbox.sql:610-652',
        },
        {
          control: 'Idempotent replay.',
          how: 'Notes and orders carry unique idempotency keys, and the Delta consumer merges events by event ID with a persisted watermark, so retries do not duplicate records.',
          enforcedIn: 'db/migrations/005_agent_runtime.sql:15-23; agent/tools_write.py:215-256; pipelines/lakebase_analytics.py',
        },
        {
          control: 'Paper placement rechecks trusted state.',
          how: 'Placement locks the order, then requires a recorded human approval, a buying-power account and risk-engine checks before calling the paper broker.',
          enforcedIn: 'agent/tools_write.py:513-694; agent/guardrails.py',
        },
      ],
    },
    {
      id: 'engineering',
      heading: 'CI checks every push and pull request, but does not prove deployment.',
      conclusion:
        'Automated gates cover tests, types, secrets and dependencies; a green run shows the code passed those checks, not that a service is running.',
      items: [
        {
          control: 'Offline test suite.',
          how: 'CI runs the Python suite without Spark, Lakebase or Databricks dependencies, plus the streaming bundle tests.',
          enforcedIn: '.github/workflows/ci.yml:54-59',
        },
        {
          control: 'Frontend type-check and build.',
          how: 'The frontend job runs the TypeScript compiler and a production build.',
          enforcedIn: '.github/workflows/ci.yml:93-101',
        },
        {
          control: 'Secret scanning and dependency audit.',
          how: 'Gitleaks scans for committed secrets; pip-audit and npm audit check dependencies, with accepted risks documented and justified.',
          enforcedIn: '.github/workflows/ci.yml:135-210; docs/SECURITY.md:22-32',
        },
        {
          control: 'Bundle validation requires credentials.',
          how: 'Databricks bundle validation is skipped, with an explicit message, when workspace credentials are absent.',
          enforcedIn: '.github/workflows/ci.yml:104-132',
        },
        {
          control: 'Mutation evidence for safety properties.',
          how: 'Point-in-time tests include deliberately weakened predicates that must fail, so a regression in leakage control breaks the suite.',
          enforcedIn: 'tests/ml/test_baseline_labels.py:569-628; tests/gold/test_pit_leakage.py; AGENTS.md',
        },
      ],
    },
  ],
  limitations: {
    heading: 'Known limitations bound what this evidence can support.',
    intro:
      'Each limitation is as much a part of the case as the controls above; none is hidden behind a capability claim.',
    items: [
      {
        limit: 'Data does not refresh itself.',
        impact: 'Market data was last ingested around 2026-09-02; scheduled incremental ingestion is planned, analytics refresh on demand, and streaming DLT is built but not deployed.',
      },
      {
        limit: 'SEC coverage is partial.',
        impact: 'Only 230 of 558 coverage tickers have filing chunks, so the agent cannot cite filings for the rest.',
      },
      {
        limit: 'XBRL fundamentals are a five-ticker pilot.',
        impact: '70,212 of 129,822 facts are quarantined, bronze/silver work is not fully merged, and gold quarterly fundamentals are planned.',
      },
      {
        limit: 'Macro history is revised, not vintage.',
        impact: 'Revised Federal Reserve and FRED series use ingest time as availability and must not be treated as known on their historical dates.',
      },
      {
        limit: 'Split-adjusted price levels are current-scale.',
        impact: 'Adjusted levels reflect later splits, so they are approved for return calculations only, not as historical price-level features.',
      },
      {
        limit: 'Options greeks exist only for the quote-snapshot date.',
        impact: 'Implied volatility, open interest and delta exposure are empty on every other date and are deliberately not forward-filled, so they cannot support historical options research.',
      },
      {
        limit: 'Per-step agent audit is not persisted by default.',
        impact: 'Executed writes are recorded in agent_actions, but the runtime audit sink defaults to a no-op, so refused proposals leave no database record.',
      },
      {
        limit: 'The standalone leakage guard skips missing timestamps.',
        impact: 'Rows lacking an availability or prediction timestamp pass gold/pit_guard.py unflagged; SEC retrieval, by contrast, excludes them.',
      },
      {
        limit: 'Results and execution are demonstrations.',
        impact: 'The baseline has no validated trading edge, and the IBKR bridge is a paper scaffold returning placeholder broker responses; nothing reaches a live market.',
      },
    ],
  },
};

// ── Features page section: research roadmap (key-line argument 2, not built) ─

export const NEXT_APPROACH: NextApproach = {
  eyebrow: 'Business case · Features · Research roadmap',
  title: 'The baseline is not the strategy; the intended ranking strategy is not yet built.',
  governingThought:
    'The published logistic baseline proves the pipeline end to end; it is not the strategy. The intended approach ranks stocks against each other on point-in-time, factor-neutral inputs and judges them after costs on data reserved in advance. None of that strategy is implemented yet.',
  statusLabel: 'Not yet implemented',
  statusNote:
    'Some building blocks exist in code and tests, mostly exercised on synthetic data or in research runners. The integrated strategy, its models and its untouched evaluation are not started. Nothing in this section is a performance claim.',
  insteadOf: {
    from: 'An untuned one-trading-day up-or-down classifier, used only to prove that features flow through a model into published signals.',
    to: 'A model that ranks stocks against each other each day, plus a separate residual-momentum test, both judged after costs on an untouched out-of-sample period.',
  },
  whatExistsToday: {
    heading: 'Building blocks exist in code, but none establishes a trading edge.',
    intro:
      'Each item states what is built and where it is used today. Most are tested library functions that the published baseline does not use.',
    items: [
      {
        title: 'Purged, embargoed walk-forward validation is built and tested.',
        text: 'It drops training rows whose label window overlaps validation and embargoes the days after it. The synthetic ablation and the reversion research runner use it; the published baseline uses a single purged time split instead.',
        evidence: 'ml/train.py:68-120,236-239; strategies/run_residual_reversion.py:437-445; tests/ml/test_walk_forward.py:42-72; scripts/publish_baseline_signals.py:16-19',
      },
      {
        title: 'Label, weighting and neutralisation code is built but has run only on synthetic data.',
        text: 'Triple-barrier labels, average-uniqueness weights and beta/industry feature neutralisation are unit-tested. Only the ablation training path uses them, with triple-barrier labels as an option and fixed labels as the default; the published baseline uses none.',
        evidence: 'ml/features.py:330-414,498-543; ml/train.py:229-297; ml/run_ablation.py:82,98-115; tests/ml/test_hardening.py:17-69',
      },
      {
        title: 'Rank-IC, outcome and performance reporting functions exist but are not yet wired in.',
        text: 'Daily rank information coefficient is computed only inside the synthetic ablation. A risk-outcome ledger with volatility frozen at prediction time, and a report that withholds Sharpe, Sortino and Calmar on short samples, are called only by their tests.',
        evidence: 'ml/evaluate.py:71-94,306-307; ml/risk_outcomes.py:1-6,20-42; strategies/report.py:21-55; tests/ml/test_risk_outcomes.py; tests/strategies/test_report.py',
      },
      {
        title: 'Residual mean-reversion research on real data finds no evidence of a tradable edge.',
        text: 'Its backtest neutralises beta and industry exposure, caps participation in daily volume and charges costs plus an assumed borrow fee. The latest report is roughly flat after costs, has no untouched holdout and understates its trial count.',
        evidence: 'strategies/residual_reversion.py:1-15; strategies/backtest.py:131-153,340-352; strategies/cost_model.py:1-40; strategies/results/residual_reversion_r10.md:64-79',
      },
      {
        title: 'The recorded A/B/C/D feature comparison is a synthetic pipeline check, not a finding.',
        text: 'It ran on generated data because the gold tables were empty when it was built. Its deflated Sharpe helper, also used by the reversion report, is marked research-only and known to be biased optimistic.',
        evidence: 'ml/results/ablation_abcd.md:1-10; ml/evaluate.py:97-131; strategies/run_residual_reversion.py:152-154',
      },
    ],
  },
  whatWeIntendToDo: {
    heading: 'Eight steps are still to do, in dependency order; none is finished.',
    intro:
      'Each step names a proposed artifact, which does not exist yet, and the evidence that would show it works. Partly built means supporting code exists; it does not mean the step is done.',
    orderingLogic:
      'Evaluation rules come first, so no later result can shape them; then the research inputs; then the models that use those inputs; then the portfolio that trades their output. The reserved period is opened once, last.',
    steps: [
      {
        id: 'protocol',
        order: 1,
        title: 'Reserve an untouched evaluation period and register every trial.',
        text: 'Fix the research questions, cost assumptions and a reserved out-of-sample period before any tuning, and log every configuration tried, including abandoned ones.',
        whyItMatters: 'Results seen during development cannot double as an independent test, and an incomplete trial count makes overfitting look like skill.',
        proposedArtifact: 'Proposed, not created: ml/holdout.py (reserved-period guard) and ml/results/trial_register.md (log of every configuration tried).',
        acceptance: 'Reserved dates are recorded before any experiment, a test fails if training or tuning code reads them, and every reported result cites its register entry.',
        dependsOn: [],
        status: 'not-started',
        existsToday: 'No period is reserved. The latest reversion report states that all of its data was seen during development.',
        stillToDo: 'The reserved period, the guard that enforces it and the trial register.',
        evidence: 'strategies/results/residual_reversion_r10.md:73-76',
      },
      {
        id: 'validation',
        order: 2,
        title: 'Add combinatorial purged validation and a corrected overfitting check.',
        text: 'Extend the purged splitter to combinatorial paths, giving a distribution of out-of-sample results, and replace the deflated Sharpe helper with a corrected implementation plus the probability of backtest overfitting.',
        whyItMatters: 'A single walk-forward path gives one number; many paths and a multiple-testing penalty show how fragile that number is.',
        proposedArtifact: 'Proposed, not created: ml/cpcv.py (combinatorial purged splits) and ml/overfitting.py (deflated Sharpe ratio and probability of backtest overfitting).',
        acceptance: 'Leakage tests like the existing walk-forward tests pass on every combinatorial split; new tests pin per-period Sharpe inputs, and the deflated Sharpe falls as the registered trial count rises.',
        dependsOn: ['protocol'],
        status: 'partly-built',
        existsToday: 'Purged, embargoed walk-forward splits exist and are tested. A deflated Sharpe helper exists but is quarantined as research-only because it mixes annualised and per-period terms.',
        stillToDo: 'Combinatorial splits, a corrected deflated Sharpe and the probability of backtest overfitting.',
        evidence: 'ml/train.py:68-120; ml/evaluate.py:97-131; tests/ml/test_walk_forward.py:42-72; tests/ml/test_hardening.py:124-128',
      },
      {
        id: 'dataset',
        order: 3,
        title: 'Build a point-in-time, factor-neutral ranking dataset from market data.',
        text: 'Assemble a daily cross-section from the gold model features with point-in-time close pairs, triple-barrier labels for the holding period, uniqueness weights and beta/industry-neutralised features.',
        whyItMatters: 'A ranking should not pass off a known market or industry exposure as skill, or learn from information that was not yet public.',
        proposedArtifact: 'Proposed, not created: ml/ranking_dataset.py (builder for the real-data daily cross-section).',
        acceptance: 'The existing look-ahead guard passes on the real matrix, daily coverage is reported, and neutralised features show no remaining beta or industry loading on real data.',
        dependsOn: ['protocol'],
        status: 'partly-built',
        existsToday: 'Close pairing, triple-barrier labels, uniqueness weights, neutralisation and a look-ahead guard exist; the ablation feeds them generated data only.',
        stillToDo: 'A real-data builder that joins these pieces, with coverage checks on the actual cross-section.',
        evidence: 'ml/baseline_labels.py:85-116; ml/features.py:265-414,498-543; ml/run_ablation.py:98-115',
      },
      {
        id: 'ranking',
        order: 4,
        title: 'Train models that rank stocks, not classifiers that call direction.',
        text: 'Start with a regularised linear comparator on neutralised features, then train a rank objective such as LambdaRank and a LightGBM challenger with equal tuning budgets, comparing market-only features with added options and filing features.',
        whyItMatters: 'A long/short book earns from relative ordering, which rank-IC measures more directly than accuracy on up-or-down calls.',
        proposedArtifact: 'Proposed, not created: ml/rank_model.py (rank-objective trainer and LightGBM challenger) and a real-data comparison report under ml/results/.',
        acceptance: 'Daily rank-IC with its uncertainty is reported per purged fold for every feature set and model, against the linear comparator, with every run logged in the trial register.',
        dependsOn: ['validation', 'dataset'],
        status: 'not-started',
        existsToday: 'Only logistic-regression and XGBoost classifiers exist. LightGBM appears solely as a configuration value; no code trains it.',
        stillToDo: 'The rank-objective trainer, the LightGBM challenger and the real-data feature comparison.',
        evidence: 'ml/train.py:125-152; strategies/config.yaml:70-72',
      },
      {
        id: 'meta-label',
        order: 5,
        title: 'Add a meta-labelling model that decides whether to act and how large.',
        text: 'Train a secondary model on the ranking model’s proposed trades, predicting which to take and at what size, with triple-barrier outcomes as its targets.',
        whyItMatters: 'Position sizing becomes something learned and tested rather than tuned by hand.',
        proposedArtifact: 'Proposed, not created: ml/meta_label.py (secondary take-or-skip and sizing model).',
        acceptance: 'On purged validation, the trades it keeps earn more after costs per unit of risk than the primary model alone; otherwise it is dropped and the result recorded.',
        dependsOn: ['ranking'],
        status: 'not-started',
        existsToday: 'Nothing: training collapses triple-barrier labels into a single up-or-not target, and no secondary model exists.',
        stillToDo: 'The secondary model, its targets and its comparison with the primary model.',
        evidence: 'ml/train.py:229-232',
      },
      {
        id: 'momentum',
        order: 6,
        title: 'Test residual momentum as a hypothesis separate from residual reversion.',
        text: 'Use the existing market and industry residuals to test whether residual moves continue rather than reverse, with its own rules, costs and validation, so it does not inherit the reversion baseline’s tuning.',
        whyItMatters: 'The strategy document titles reversion rules as momentum; the two imply opposite trades and need separate evidence.',
        proposedArtifact: 'Proposed, not created: strategies/residual_momentum.py (continuation signal) and a results file under strategies/results/.',
        acceptance: 'It runs through the same backtest, costs and purged walk-forward as the reversion baseline, and its report is published whatever the outcome.',
        dependsOn: ['protocol', 'validation'],
        status: 'partly-built',
        existsToday: 'Market and industry residual computation and a residual mean-reversion backtest exist; no continuation rule exists.',
        stillToDo: 'Continuation rules, their evaluation and a single, consistent strategy definition in the documentation.',
        evidence: 'strategies/residual_reversion.py:1-15,61-90; docs/QUANT_STRATEGIES.md:32-47',
      },
      {
        id: 'portfolio',
        order: 7,
        title: 'Construct constrained portfolios and stress them for costs.',
        text: 'Turn rankings into weights with beta and industry neutrality, position caps and a turnover penalty, using shrunk covariance or hierarchical risk parity, then stress slippage, market impact and borrow assumptions.',
        whyItMatters: 'Predictive ordering has no economic value if an implementable portfolio loses it to costs.',
        proposedArtifact: 'Proposed, not created: strategies/portfolio.py (constrained optimiser with covariance shrinkage and a risk-parity alternative).',
        acceptance: 'Realised beta and industry exposures stay near zero, and results are reported gross, net and with doubled costs, including the borrow assumption and a market-impact estimate.',
        dependsOn: ['ranking', 'meta-label', 'momentum'],
        status: 'partly-built',
        existsToday: 'The backtest neutralises the book, caps volume participation and charges linear costs and borrow. A square-root market-impact function exists, but the backtest does not call it.',
        stillToDo: 'The optimiser, covariance shrinkage, the risk-parity alternative, the turnover penalty and impact-based cost stress.',
        evidence: 'strategies/backtest.py:131-153,340-352; strategies/cost_model.py:173-196; strategies/neutralize.py:55-65',
      },
      {
        id: 'final-evaluation',
        order: 8,
        title: 'Evaluate the frozen design once on the reserved period, then decide.',
        text: 'Freeze models, rules and costs, run once on the reserved period, and report rank-IC, cost-adjusted returns and the corrected deflated Sharpe alongside every registered trial, including failures.',
        whyItMatters: 'Only a single pass on unseen data can support or reject an edge; repeated looks would use up that independence.',
        proposedArtifact: 'Proposed, not created: a final evaluation report under strategies/results/ that cites the trial register.',
        acceptance: 'One recorded run on the reserved period, published whatever the result; new signals are published only if that evidence supports them and the owner approves.',
        dependsOn: ['protocol', 'validation', 'portfolio'],
        status: 'not-started',
        existsToday: 'Nothing: no period is reserved, and only the 35 baseline signals are published.',
        stillToDo: 'The frozen design, the single reserved-period run and the publish-or-stop decision.',
        evidence: 'docs/BUSINESS_CASE.md:4,28; strategies/results/residual_reversion_r10.md:76-79',
      },
    ],
  },
  studies: {
    heading: 'The roadmap draws on studies and methods the repository already cites.',
    intro:
      'Authors and years appear only where the repository states them. No study has been reproduced here, and citing one is not evidence that its method works on this data.',
    items: [
      {
        name: 'Avellaneda–Lee eigenportfolios',
        usedFor: 'Statistical factors from principal components of return correlations, as an alternative to market and industry regressions when computing residuals.',
        inCodeToday: 'Not built; the reversion baseline uses market and industry factors.',
        citedIn: 'docs/QUANT_STRATEGIES.md:64-70',
      },
      {
        name: 'Ledoit–Wolf covariance shrinkage',
        usedFor: 'Stabilising a covariance matrix estimated from many stocks over comparatively few days, before factor extraction and portfolio optimisation.',
        inCodeToday: 'Not built.',
        citedIn: 'docs/QUANT_STRATEGIES.md:68-70,276-277',
      },
      {
        name: 'Hierarchical risk parity',
        usedFor: 'A shrinkage-free alternative to constrained mean-variance portfolio construction.',
        inCodeToday: 'Not built.',
        citedIn: 'docs/QUANT_STRATEGIES.md:278-279',
      },
      {
        name: 'Foster (1977); Bernard & Thomas (1989): seasonal-random-walk earnings surprise',
        usedFor: 'Measuring post-earnings drift from reported earnings history alone, because no analyst estimates exist in the data.',
        inCodeToday: 'Not built and outside the eight roadmap steps; it needs quarterly earnings from XBRL, which remains a five-ticker pilot.',
        citedIn: 'docs/QUANT_STRATEGIES.md:191-202',
      },
      {
        name: 'Bailey and Lopez de Prado deflated Sharpe ratio',
        usedFor: 'Penalising a Sharpe ratio for the number of configurations tried.',
        inCodeToday: 'A helper exists and feeds the research reports, but is marked known-unreliable; a corrected version is roadmap step two.',
        citedIn: 'ml/evaluate.py:97-131; strategies/backtest.py:298-300; strategies/run_residual_reversion.py:569; docs/QUANT_STRATEGIES.md:261-262',
      },
      {
        name: 'Probability of backtest overfitting',
        usedFor: 'Penalising the multiple testing implicit in comparing several feature sets.',
        inCodeToday: 'Not built.',
        citedIn: 'docs/QUANT_STRATEGIES.md:261-262',
      },
      {
        name: 'Almgren-Chriss temporary market impact',
        usedFor: 'Estimating the price impact of an order from its size relative to daily volume and from volatility.',
        inCodeToday: 'A square-root impact function exists; the reversion backtest does not use it.',
        citedIn: 'strategies/cost_model.py:173-196',
      },
      {
        name: 'Purged and embargoed walk-forward validation',
        usedFor: 'Removing training rows whose label windows overlap validation, plus a buffer after it.',
        inCodeToday: 'Built and tested; used by the synthetic ablation and the reversion runner.',
        citedIn: 'docs/QUANT_STRATEGIES.md:228-237; ml/train.py:68-120',
      },
      {
        name: 'Triple-barrier labelling and meta-labelling',
        usedFor: 'Path-dependent labels from a profit target, stop loss and time limit; a secondary model that decides whether to take a signal and at what size.',
        inCodeToday: 'Triple-barrier labels built, run on synthetic data only; meta-labelling not built.',
        citedIn: 'docs/QUANT_STRATEGIES.md:239-244; ml/features.py:330-386',
      },
      {
        name: 'Average-uniqueness weighting and sequential bootstrap',
        usedFor: 'Down-weighting overlapping labels, and resampling that respects that overlap when bagging.',
        inCodeToday: 'Uniqueness weights built, run on synthetic data only; sequential bootstrap not built.',
        citedIn: 'docs/QUANT_STRATEGIES.md:246-249; ml/features.py:389-414',
      },
      {
        name: 'Factor-neutralised features',
        usedFor: 'Residualising each feature against beta and industry so a model cannot win by loading on a known factor.',
        inCodeToday: 'Built and tested; run on synthetic data only.',
        citedIn: 'docs/QUANT_STRATEGIES.md:258-260; ml/features.py:498-543',
      },
      {
        name: 'Rank information coefficient and LambdaRank',
        usedFor: 'Measuring, and training for, the daily relative ordering of stocks rather than per-name direction.',
        inCodeToday: 'A daily rank-IC evaluator exists; no LambdaRank or other rank-objective model exists.',
        citedIn: 'docs/QUANT_STRATEGIES.md:251-256; ml/evaluate.py:71-94',
      },
      {
        name: 'Combinatorial purged cross-validation',
        usedFor: 'A distribution of out-of-sample paths rather than a single estimate.',
        inCodeToday: 'Not built.',
        citedIn: 'docs/QUANT_STRATEGIES.md:263-264',
      },
    ],
  },
  howWeWillJudgeIt: {
    heading: 'No edge will be claimed without predictive and economic evidence on unseen data.',
    intro: 'These are intended standards, not results. None has yet been applied to the intended strategy.',
    items: [
      'Predictive: daily rank information coefficient per purged fold, with its stability and uncertainty, compared with a simple comparator.',
      'Economic: returns after costs, turnover and drawdown, reported gross, net and with doubled costs, with borrow stated as an explicit assumption.',
      'Overfitting: a corrected deflated Sharpe ratio and the probability of backtest overfitting, computed from the complete trial register.',
      'Independence: one run of the frozen design on an out-of-sample period that no development step has touched.',
      'Disclosure: no performance claim and no new published signals before that run, and failed results reported as fully as successes.',
    ],
  },
  honestOutlook: {
    heading: 'The research may find no edge; the platform’s value does not depend on one.',
    text: 'The latest reversion research already found no tradable edge, and the intended approach may find none either. The business case rests on governed inputs, traceable research and audited actions, which hold whether or not a strategy succeeds.',
  },
};

export const NAV_LINKS: NavigationLinks = {
  overview: 'Overview',
  data: 'Data',
  features: 'Features',
  controls: 'Controls',
};
