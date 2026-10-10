// Business Case content (Overview, Data, Infrastructure, Features, Controls, Rubric).
// Static snapshot measured 2026-10-06; platform figures are copied from docs/BUSINESS_CASE.md.
// Study years in NEXT_APPROACH are copied from docs/QUANT_STRATEGIES.md; no strategy-result figure is quoted.
// INFRASTRUCTURE also copies counts from docs/proposal/row_counts_2026-10-05.tsv, each labelled with its own as-of time.
// RUBRIC_AI is a self-assessment against the owner-supplied official rubric; its point ranges are judgements, not data.
// Edited final v3: earlier exports keep their names and shapes; fields and exports are only added.
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

// Supporting page that deepens one key-line argument (Infrastructure deepens Data).
export type DetailPage = 'infrastructure';

// Cross-cutting page that judges the whole case; it is not a key-line argument.
export type AssessmentPage = 'rubric';

// Every Business Case page, in navigation order.
export type BusinessCasePage = 'overview' | 'data' | 'infrastructure' | 'features' | 'controls' | 'rubric';

export interface KeyLine {
  governingThought: string;
  orderingLogic: string;
  arguments: {
    id: EvidencePage;
    claim: string;
    proof: string;
    page: EvidencePage;
    detailPages: DetailPage[];
  }[];
  assessment: { label: string; text: string; page: AssessmentPage };
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
  infrastructure: string;
  features: string;
  controls: string;
  rubric: string;
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
    'Process order, following the data: what goes in (Data, with its pipeline on Infrastructure), what the platform does with it (Features), and why its output can be trusted and where it cannot (Controls).',
  arguments: [
    {
      id: 'data',
      claim: 'The platform holds real market, options and filing data at research scale.',
      proof:
        '48 tables, including 152,104,694 daily option rows, 23,420,557 minute bars and 133,886 SEC chunks with embeddings, measured on 2026-10-06.',
      page: 'data',
      detailPages: ['infrastructure'],
    },
    {
      id: 'features',
      claim: 'The workflow is built end to end; the intended strategy is not yet built.',
      proof:
        'Ingestion, cleaning, features, retrieval, the agent, baseline signals and audit exist in code; scheduled ingestion, streaming deployment, placeholder screens and the intended ranking strategy do not, and a research roadmap names what is still to do.',
      page: 'features',
      detailPages: [],
    },
    {
      id: 'controls',
      claim: 'Point-in-time, agent and engineering controls are enforced in code, with their limits stated.',
      proof:
        'Agent writes pass a typed schema, an allowlist, request-scoped authorisation and a role check before deterministic execution and an audit record; known limitations are listed alongside.',
      page: 'controls',
      detailPages: [],
    },
  ],
  assessment: {
    label: 'How the case would be judged',
    text: 'The Rubric page scores all three arguments against the official capstone rubric as a conservative range, naming every item that cannot be verified offline. It is a self-assessment, not a grade.',
    page: 'rubric',
  },
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
    'A dated inventory of 48 tables shows the inputs are real and sized, and shows equally plainly where data is stale, partial or still planned. The Infrastructure page shows how each source reaches Bronze, Silver and Gold.',
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
          note: 'Row counts were not measured at this snapshot. Revised series use ingest time as availability and are not first-release vintage data.',
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
  infrastructure: 'Infrastructure',
  features: 'Features',
  controls: 'Controls',
  rubric: 'Rubric self-assessment',
};

// ── Data page section: infrastructure (key-line argument 1, how the inputs got there) ─

export type InfrastructureLayerId = 'bronze' | 'silver' | 'gold' | 'serving';

export type FunnelStage = 'bronze' | 'filter' | 'silver' | 'gold';

export type InfrastructureFutureStatus = 'planned' | 'built-not-deployed' | 'blocked-on-owner';

export interface Infrastructure {
  eyebrow: string;
  title: string;
  governingThought: string;
  flow: { id: string; label: string; role: string; evidence: string }[];
  sources: { name: string; whatItProvides: string; howObtained: string; lands: string; evidence: string }[];
  layers: {
    id: InfrastructureLayerId;
    heading: string;
    conclusion: string;
    items: { name: string; what: string; rowsLabel?: string; asOf?: string; evidence: string }[];
  }[];
  funnel: {
    heading: string;
    intro: string;
    steps: { stage: FunnelStage; label: string; count: string; asOf: string; note: string; source: string }[];
    caveat: string;
  };
  whyNotEverythingIsInSilver: {
    heading: string;
    text: string;
    points: { text: string; evidence: string }[];
  };
  future: {
    heading: string;
    intro: string;
    items: {
      id: string;
      title: string;
      text: string;
      status: InfrastructureFutureStatus;
      existsToday: string;
      stillToDo: string;
      evidence: string;
    }[];
  };
}

export const INFRASTRUCTURE: Infrastructure = {
  eyebrow: 'Business case · Data · Infrastructure',
  title: 'Inputs land raw in Bronze; Silver and Gold narrow them to time-tagged research data.',
  governingThought:
    'Batch jobs land seven external sources in Bronze with lineage intact. Silver and Gold work on a deliberately narrow 39-symbol research universe, and every Gold feature carries the time it became available. Counts are dated; no ingestion schedule is active.',
  flow: [
    {
      id: 'sources',
      label: 'External sources',
      role: 'Massive flat files and REST, Polygon REST, SEC EDGAR, CFTC and FRED supply batch inputs; provider keys come from a Databricks secret scope or environment variables.',
      evidence: 'notebooks/refresh_bronze_equities.py:293-294; notebooks/refresh_bronze_options.py:385-399; pipelines/sec_rag_ingest.py:86-95',
    },
    {
      id: 'bronze',
      label: 'Bronze landing',
      role: 'Refresh jobs append only new data, skipping files or keys already loaded, and log every source file; SEC filings use an insert-only MERGE on accession number.',
      evidence: 'notebooks/refresh_bronze_equities.py:1-20; notebooks/refresh_bronze_options.py:1-30; pipelines/sec_rag_ingest.py:2133-2140',
    },
    {
      id: 'universe',
      label: 'Research-universe filter',
      role: 'The orchestrator registers the 39 symbols in config/universe.yaml as the universe view that the market and options transforms filter on.',
      evidence: 'pipelines/run_silver_gold.py:86-96; config/universe.yaml; gold/05_gold_model_features.sql:8-9',
    },
    {
      id: 'silver',
      label: 'Silver cleaning',
      role: 'SQL MERGE transforms type, deduplicate and range-check records; bars that fail a rule go to a quarantine table instead of the clean layer.',
      evidence: 'silver/01_silver_ohlcv.sql:1-19; silver/02_silver_ohlcv_quarantine.sql:1-10',
    },
    {
      id: 'gold',
      label: 'Gold features',
      role: 'Features record when their information became available, and the build fails if any joined feature postdates its prediction time.',
      evidence: 'gold/05_gold_model_features.sql:13-23; pipelines/run_silver_gold.py:177-284',
    },
    {
      id: 'serving',
      label: 'Analytical serving',
      role: 'A parameterised, bounded SQL-warehouse adapter feeds FastAPI routes, the React screens and the agent’s read tools.',
      evidence: 'db/delta_adapter.py:190-221; agent/tools_retrieval.py:127-168',
    },
    {
      id: 'operational',
      label: 'Operational writes',
      role: 'Lakebase (Postgres) stores watchlists, notes, orders, approvals and agent actions; each change writes an outbox event in the same transaction.',
      evidence: 'db/migrations/001_operational_schema.sql:18-145; db/migrations/004_analytics_outbox.sql:610-652',
    },
    {
      id: 'analytics',
      label: 'Activity analytics',
      role: 'A job claims pending outbox events, merges them into Delta by event ID, rebuilds the affected daily aggregates, then marks the events delivered.',
      evidence: 'pipelines/lakebase_analytics.py:1-12,598-652; db/migrations/CDC.md',
    },
  ],
  sources: [
    {
      name: 'Massive equities',
      whatItProvides: 'Minute and daily US equity bars.',
      howObtained: 'S3 flat files read with keys from a Databricks secret scope. Daily files load the full market; minute files load a fixed ticker list set in the refresh notebook.',
      lands: 'bronze_ohlcv; bronze_ohlcv_day; massive_ingestion_log; massive_daily_ingestion_log',
      evidence: 'notebooks/refresh_bronze_equities.py:1-20,44-45,58-70,293-294',
    },
    {
      name: 'Massive options',
      whatItProvides: 'Daily per-contract option aggregates.',
      howObtained: 'S3 flat files; a date outside the data entitlement is logged as a gap, never filled.',
      lands: 'bronze_options_day; massive_ingestion_log',
      evidence: 'notebooks/refresh_bronze_options.py:5-11,662-681',
    },
    {
      name: 'Massive corporate actions',
      whatItProvides: 'Stock splits used to adjust daily prices.',
      howObtained: 'REST API that retries with backoff on rate-limit and server errors, stops on authorisation errors and drops malformed split rows.',
      lands: 'bronze_corporate_actions; corporate_actions_ingestion_log',
      evidence: 'etl/corporate_actions.py:208-290; notebooks/refresh_bronze_corporate_actions.py:1-22',
    },
    {
      name: 'Polygon',
      whatItProvides: 'A current option-chain snapshot with implied volatility and greeks.',
      howObtained: 'REST snapshot endpoint; only the snapshot actually returned is stored, and no historical snapshot is fabricated.',
      lands: 'bronze_options_quotes',
      evidence: 'notebooks/refresh_bronze_options.py:13-20',
    },
    {
      name: 'SEC EDGAR',
      whatItProvides: '10-K and 10-Q filing text.',
      howObtained: 'HTTP requests with a declared User-Agent held as a secret, a shared rate limiter, Retry-After handling and exponential backoff.',
      lands: 'bronze_sec_filings_v2; sec_ingest_log',
      evidence: 'pipelines/sec_rag_ingest.py:86-95,700-712,839-871',
    },
    {
      name: 'CFTC',
      whatItProvides: 'Traders in Financial Futures positioning reports.',
      howObtained: 'Annual report archives downloaded over HTTPS and appended to Bronze.',
      lands: 'bronze_cftc_fut; bronze_cftc_com',
      evidence: 'notebooks/refresh_bronze_cot.py:1-11,69,117-134',
    },
    {
      name: 'Federal Reserve / FRED',
      whatItProvides: 'Rates and macroeconomic series.',
      howObtained: 'Public CSV downloads with retries and header validation, appended to Bronze. History is revised, not first-release vintage.',
      lands: 'bronze_fed_series',
      evidence: 'notebooks/refresh_bronze_fed.py:1-9,194-215,422-430; docs/BUSINESS_CASE.md:48',
    },
  ],
  layers: [
    {
      id: 'bronze',
      heading: 'Bronze keeps whole-market history, far more than research uses today.',
      conclusion: 'Refresh jobs append only new data, log each source file and record entitlement gaps instead of filling them.',
      items: [
        {
          name: 'Equity bars',
          what: 'Daily files cover the full market; minute files cover the fixed ticker list in the refresh notebook.',
          rowsLabel: '73298082 minute rows; 13219248 daily rows',
          asOf: '2026-10-05T03:41:23 UTC',
          evidence: 'docs/proposal/row_counts_2026-10-05.tsv:1,8-9; notebooks/refresh_bronze_equities.py:58-70',
        },
        {
          name: 'Daily option aggregates',
          what: 'Per-contract daily option history from Massive flat files: the largest table in the lakehouse.',
          rowsLabel: '152,104,694 rows',
          asOf: '2026-10-06 ~09:30 SGT',
          evidence: 'docs/BUSINESS_CASE.md:4,39; notebooks/refresh_bronze_options.py:8-11',
        },
        {
          name: 'SEC filings',
          what: '10-K and 10-Q text since 2024-09, stored as section chunks and merged insert-only by accession number.',
          rowsLabel: '191,248 rows; 225 tickers; 2,845 filings',
          asOf: '2026-10-06 ~09:30 SGT',
          evidence: 'docs/BUSINESS_CASE.md:45; pipelines/sec_rag_ingest.py:2133-2140',
        },
        {
          name: 'Positioning and macro',
          what: 'CFTC futures-only and combined reports and FRED series, appended as downloaded.',
          evidence: 'notebooks/refresh_bronze_cot.py:1-11; notebooks/refresh_bronze_fed.py:422-430',
        },
      ],
    },
    {
      id: 'silver',
      heading: 'Silver cleans a 39-symbol research universe, not the whole Bronze market.',
      conclusion: 'Market transforms filter to config/universe.yaml, and every transform is a MERGE on a stable key, so a re-run updates rows rather than duplicating them.',
      items: [
        {
          name: 'Minute bars',
          what: 'Typed, UTC-stamped bars deduplicated by hash; only bars with non-null prices, consistent ranges and non-negative volume enter.',
          rowsLabel: '23,420,557 rows',
          asOf: '2026-10-06 ~09:30 SGT',
          evidence: 'docs/BUSINESS_CASE.md:4,38; silver/01_silver_ohlcv.sql:1-19,60-79',
        },
        {
          name: 'Quarantine',
          what: 'Bars that fail a range or null rule go to a separate batch quarantine table, which held no rows at the dated count.',
          rowsLabel: '0 rows',
          asOf: '2026-10-05T03:41:23 UTC',
          evidence: 'silver/02_silver_ohlcv_quarantine.sql:1-10; docs/proposal/row_counts_2026-10-05.tsv:35',
        },
        {
          name: 'Option trades and quotes',
          what: 'Trades come from bronze_options_trades. The quote snapshot keeps greeks, but its bid and ask fields are empty in every row.',
          rowsLabel: '60,068 trade rows',
          asOf: '2026-10-06 ~09:30 SGT',
          evidence: 'docs/BUSINESS_CASE.md:39; silver/04_silver_options_trades.sql:1-11; silver/03_silver_options_quotes.sql:1-9',
        },
        {
          name: 'SEC sections and adjusted daily prices',
          what: 'These use the wider Gold tradable universe instead: SEC adds a fixed list of semiconductor tickers, and adjusted prices add SPY, RSP and QQQ.',
          evidence: 'silver/05_silver_sec_sections.sql:14-30; silver/08_silver_ohlcv_day_adjusted.sql:115-130',
        },
      ],
    },
    {
      id: 'gold',
      heading: 'Gold attaches availability times, and the build fails on any look-ahead.',
      conclusion: 'Each feature records when its information became public; the orchestrator raises an error if a joined feature postdates its prediction time.',
      items: [
        {
          name: 'Minute features',
          what: 'A minute bar becomes available one minute after it opens, and that availability time is the point-in-time key.',
          rowsLabel: '23,377,478 rows',
          asOf: '2026-10-06 ~09:30 SGT',
          evidence: 'docs/BUSINESS_CASE.md:38; gold/01_gold_ohlcv_features.sql:9-15',
        },
        {
          name: 'Options features',
          what: 'Aggregated directly from Bronze daily options for the research universe, available only after that day’s New York close plus a buffer; greeks exist only on the snapshot date.',
          rowsLabel: '20,318 rows',
          asOf: '2026-10-06 ~09:30 SGT',
          evidence: 'docs/BUSINESS_CASE.md:39; gold/02_gold_options_features.sql:1-24,28-47',
        },
        {
          name: 'Tradable universe',
          what: 'Built from Bronze daily bars using only earlier sessions: the most liquid names by trailing median dollar volume, with recency and history filters.',
          rowsLabel: '281,700 rows; 557 symbols',
          asOf: '2026-10-06 ~09:30 SGT',
          evidence: 'docs/BUSINESS_CASE.md:4,38; gold/06_gold_tradable_universe.sql:1-20',
        },
        {
          name: 'Model snapshots and SEC embeddings',
          what: 'Daily snapshots join every source as of the prediction time; SEC chunks are embedded with BAAI/bge-small-en-v1.5 for retrieval.',
          rowsLabel: '40,983 snapshots; 133,886 embeddings',
          asOf: '2026-10-06 ~09:30 SGT',
          evidence: 'docs/BUSINESS_CASE.md:4,45,54; gold/05_gold_model_features.sql:1-23; pipelines/build_sec_embeddings.py:4-5',
        },
        {
          name: 'Build-time leakage checks',
          what: 'Availability and matrix invariants count violating rows and raise an error, failing the build, if any exist.',
          evidence: 'pipelines/run_silver_gold.py:177-284',
        },
      ],
    },
    {
      id: 'serving',
      heading: 'Analytical reads and operational writes take separate, auditable paths.',
      conclusion: 'Delta serves research reads through a bounded adapter; Lakebase holds transactional state and feeds activity back to Delta through an outbox.',
      items: [
        {
          name: 'Research reads',
          what: 'FastAPI routes query Gold through a SQL-warehouse adapter with named parameters, row limits and timeouts; React screens render the results.',
          evidence: 'db/delta_adapter.py:190-221; api/routes/market.py; frontend/src/api/client.ts',
        },
        {
          name: 'Agent retrieval',
          what: 'Four read tools query signals, market and options features, and hybrid BM25 and vector search over SEC chunks filtered by acceptance time.',
          evidence: 'agent/contracts.py:203-209; agent/tools_retrieval.py:127-168; api/services/hybrid_retriever.py:15-20',
        },
        {
          name: 'Operational state and analytics',
          what: 'Lakebase writes add an outbox event in the same transaction; a single-concurrency job merges events into Delta by event ID and only then marks them delivered.',
          evidence: 'db/migrations/004_analytics_outbox.sql:610-652; pipelines/lakebase_analytics.py:598-652',
        },
        {
          name: 'Job definitions',
          what: 'Bundle jobs define daily Silver/Gold and analytics refreshes, but both schedules are set to paused; the analytics job runs on demand.',
          evidence: 'resources/jobs.yml:3-13,130-140; docs/BUSINESS_CASE.md:56',
        },
      ],
    },
  ],
  funnel: {
    heading: 'The equity path narrows from whole-market Bronze to 35 baseline signals.',
    intro: 'One path, followed layer by layer. Grains differ between steps, so a count is not a subset of the one before, and each count shows its own as-of time.',
    steps: [
      {
        stage: 'bronze',
        label: 'Minute bars landed (bronze_ohlcv)',
        count: '73298082',
        asOf: '2026-10-05T03:41:23 UTC',
        note: 'Massive minute files for the refresh ticker list, before any cleaning.',
        source: 'docs/proposal/row_counts_2026-10-05.tsv:1,8',
      },
      {
        stage: 'filter',
        label: 'Research universe (config/universe.yaml)',
        count: '39',
        asOf: 'Configuration at this commit',
        note: 'The only symbol filter the orchestrator registers for Silver and Gold market transforms.',
        source: 'config/universe.yaml; gold/05_gold_model_features.sql:8; pipelines/run_silver_gold.py:86-96',
      },
      {
        stage: 'silver',
        label: 'Clean minute bars (silver_ohlcv)',
        count: '23,420,557',
        asOf: '2026-10-06 ~09:30 SGT',
        note: 'Typed, deduplicated, range-checked bars for the research universe.',
        source: 'docs/BUSINESS_CASE.md:4,38',
      },
      {
        stage: 'gold',
        label: 'Minute features (gold_ohlcv_features)',
        count: '23,377,478',
        asOf: '2026-10-06 ~09:30 SGT',
        note: 'Features keyed to the time each bar became available.',
        source: 'docs/BUSINESS_CASE.md:38',
      },
      {
        stage: 'gold',
        label: 'Model snapshots (gold_model_features)',
        count: '40,983',
        asOf: '2026-10-06 ~09:30 SGT',
        note: 'One row per symbol per prediction time: a coarser grain, not a filtered subset.',
        source: 'docs/BUSINESS_CASE.md:4,54',
      },
      {
        stage: 'gold',
        label: 'Baseline signals (gold_trading_signals)',
        count: '35',
        asOf: '2026-10-06 ~09:30 SGT',
        note: 'Output of an untuned logistic regression that proves the pipeline; no trading edge is claimed.',
        source: 'docs/BUSINESS_CASE.md:4,54',
      },
    ],
    caveat: 'The Bronze count comes from the 2026-10-05T03:41:23 UTC count file; the Silver and Gold counts come from the 2026-10-06 ~09:30 SGT banner. No count was re-queried for this page.',
  },
  whyNotEverythingIsInSilver: {
    heading: 'Large Bronze tables bypass Silver or have no consumer yet.',
    text: 'Silver is selective by design: it cleans what the research universe uses. These tables are real but take other paths.',
    points: [
      {
        text: 'bronze_options_day (152,104,694 rows) has no Silver table; Gold options features aggregate it directly, for the research universe only.',
        evidence: 'docs/BUSINESS_CASE.md:4; gold/02_gold_options_features.sql:1-5,70-80; silver/04_silver_options_trades.sql:1-11',
      },
      {
        text: 'Daily equity bars feed the Gold tradable universe directly from Bronze, without a Silver step.',
        evidence: 'gold/06_gold_tradable_universe.sql:1-20',
      },
      {
        text: 'config/tickers.yaml lists 12,400 tickers by industry group; it serves the symbol allow-list and industry mapping, not ingestion or Silver filtering.',
        evidence: 'docs/QUANT_STRATEGIES.md:54; agent/guardrails.py:113-120; config/universe.yaml',
      },
      {
        text: 'FRED tables and the combined CFTC report have no Silver or Gold transform; COT Silver reads only the futures-only report.',
        evidence: 'silver/07_silver_cot_positions.sql:1-5,77; pipelines/run_silver_gold.py:42-60',
      },
    ],
  },
  future: {
    heading: 'Eight infrastructure improvements are identified; none is done yet.',
    intro: 'Each item states what exists today and what is still to do. Status words are literal: planned means not started, and blocked on owner means it needs an approved live window.',
    items: [
      {
        id: 'incremental',
        title: 'Schedule incremental Bronze ingestion.',
        text: 'Not yet done. Refresh notebooks append new dates only when started by hand, so market data stops around 2026-09-02.',
        status: 'planned',
        existsToday: 'Append-only refresh notebooks with ingestion logs and entitlement-gap handling, plus written refresh plans.',
        stillToDo: 'An owner-approved schedule, completeness checks on every run and alerts on failure.',
        evidence: 'docs/BRONZE_REFRESH_PLAN.md; docs/data/PLAN-massive-incremental.md; notebooks/refresh_bronze_equities.py:1-20',
      },
      {
        id: 'job-schedules',
        title: 'Un-pause the Silver/Gold and analytics job schedules.',
        text: 'Not yet done. Both jobs are defined with daily schedules that are set to paused.',
        status: 'blocked-on-owner',
        existsToday: 'Bundle job definitions for the Silver/Gold refresh and the analytics refresh.',
        stillToDo: 'Owner approval for the running cost, then monitored scheduled runs.',
        evidence: 'resources/jobs.yml:3-13,130-140',
      },
      {
        id: 'streaming',
        title: 'Deploy the streaming pipeline and measure its latency.',
        text: 'Not yet done. The continuous pipeline is built and validated locally, but has never run.',
        status: 'built-not-deployed',
        existsToday: 'A DLT bundle that streams bronze_ohlcv into dlt_-prefixed tables and defines a latency-metrics table.',
        stillToDo: 'An approved deployment, recorded end-to-end latency, checkpoint recovery and monitoring.',
        evidence: 'bundles/streaming/README.md:1-10,26-58',
      },
      {
        id: 'options-silver',
        title: 'Give daily options a Silver layer.',
        text: 'Not yet done. Gold reads the largest Bronze table without a cleaned intermediate.',
        status: 'planned',
        existsToday: 'Gold aggregates bronze_options_day directly; Silver holds only option trades and the quote snapshot.',
        stillToDo: 'A keyed Silver transform with type, range and duplicate checks for daily contracts.',
        evidence: 'gold/02_gold_options_features.sql:1-24; silver/04_silver_options_trades.sql:1-11',
      },
      {
        id: 'wider-universe',
        title: 'Widen Silver beyond the 39-symbol research universe.',
        text: 'Not yet done. Research features cover only the configured universe, although Bronze holds the whole market.',
        status: 'planned',
        existsToday: 'Whole-market daily bars and options in Bronze; a Gold tradable universe that already ranks 557 symbols.',
        stillToDo: 'Extend the universe file, size the compute first, and re-run with coverage and point-in-time checks.',
        evidence: 'config/universe.yaml; gold/06_gold_tradable_universe.sql:1-20; docs/BUSINESS_CASE.md:4',
      },
      {
        id: 'rebuild-order',
        title: 'Make a clean rebuild independent of the previous run.',
        text: 'Not yet done. Silver SEC and adjusted-price steps read the Gold tradable universe, which the orchestrator builds later in the same run.',
        status: 'planned',
        existsToday: 'MERGE-based re-runs and an optional truncate flag for a clean backfill.',
        stillToDo: 'Build the tradable universe first, then show that a truncate-and-rebuild matches an incremental run.',
        evidence: 'pipelines/run_silver_gold.py:1-20,42-60,99-111; silver/05_silver_sec_sections.sql:22-30; silver/08_silver_ohlcv_day_adjusted.sql:122-130',
      },
      {
        id: 'freshness',
        title: 'Set freshness targets for each source.',
        text: 'Not yet done. Freshness is reported as measured, not held to a target.',
        status: 'planned',
        existsToday: 'Ingestion logs and dated counts show when data last landed; no target or alert exists.',
        stillToDo: 'Per-source freshness targets, a check after every run and alerts on misses.',
        evidence: 'docs/BUSINESS_CASE.md:32; notebooks/refresh_bronze_equities.py:44-45',
      },
      {
        id: 'live-proof',
        title: 'Re-verify the deployed path in an approved live window.',
        text: 'Not yet done for this snapshot, which asserts no running service.',
        status: 'blocked-on-owner',
        existsToday: 'The README records a deployment and live agent, write and analytics runs on 2026-10-05; the planning file records the app and Lakebase as stopped.',
        stillToDo: 'Start the services with owner approval, capture dated smoke, write and replay evidence, then stop them.',
        evidence: 'README.md:42-45; docs/rubric/PLAN.md:20-21,33',
      },
    ],
  },
};

// ── Rubric page: self-assessment against the official rubric (cross-cutting) ─

export type RubricEvidenceStrength =
  | 'demonstrated-in-repo'
  | 'partly-demonstrated'
  | 'not-demonstrated'
  | 'unverified-needs-live-proof';

export type EvidenceGapStatus = 'verified-present' | 'unverified' | 'absent';

export type RubricGapStatus = 'planned' | 'not-started';

export interface RubricAI {
  eyebrow: string;
  title: string;
  governingThought: string;
  basis: {
    heading: string;
    text: string;
    officialRubricInRepo: boolean;
    scoringRule: string;
    evidence: string;
  };
  scorecard: {
    heading: string;
    intro: string;
    rows: {
      id: string;
      category: string;
      component: string;
      pointsPossible: number;
      whatTheGraderLooksFor: string;
      evidence: string;
      evidenceStrength: RubricEvidenceStrength;
      selfAssessedBand: { low: number; high: number };
      bandReasoning: string;
      gap: string;
      unverifiedItems: string[];
    }[];
    byCategory: {
      id: string;
      category: string;
      pointsPossible: number;
      low: number;
      high: number;
      note: string;
    }[];
  };
  totals: {
    heading: string;
    possible: number;
    selfAssessedLow: number;
    selfAssessedHigh: number;
    capApplies: boolean;
    capNote: string;
    caveat: string;
    swingFactors: string[];
  };
  agent: {
    heading: string;
    intro: string;
    capabilities: { title: string; text: string; evidence: string }[];
    safetyModel: {
      heading: string;
      steps: { title: string; text: string; enforcedIn: string }[];
      caveats: string[];
    };
  };
  demoScript: {
    heading: string;
    intro: string;
    steps: { order: number; category: string; show: string; proves: string; how: string }[];
  };
  gaps: {
    heading: string;
    intro: string;
    items: {
      id: string;
      category: string;
      currentBand: string;
      nextBand: string;
      gap: string;
      concreteAction: string;
      status: RubricGapStatus;
    }[];
  };
  strengths: { heading: string; items: { title: string; text: string; evidence: string }[] };
  evidenceGaps: {
    heading: string;
    intro: string;
    items: { item: string; status: EvidenceGapStatus; evidence: string; note: string }[];
  };
}

export const RUBRIC_AI: RubricAI = {
  eyebrow: 'Business case · Rubric self-assessment',
  title: 'Against the official rubric, the evidence supports a range, not a grade.',
  governingThought:
    'Scored conservatively against the official Databricks AI Capstone Rubric, repository evidence supports 44 to 71 of 100 points. The spread reflects evidence a grader cannot re-check offline: deployment, Change Data Feed or DLT, measured latency and the live agent write.',
  basis: {
    heading: 'This is a self-assessment against the official rubric; the grader decides.',
    text: 'The official Databricks AI Capstone Rubric, eight categories worth 100 points, was supplied by the owner and is not in the repository. Each row maps repository evidence to its band descriptions; nothing here is a grade or a promised score.',
    officialRubricInRepo: false,
    scoringRule:
      'Low end: credit only what a grader can re-check from the repository today. High end: also accept the dated live runs the README records. Neither end goes beyond what the code supports.',
    evidence: 'README.md:17-49; docs/rubric/PLAN.md:23-38',
  },
  scorecard: {
    heading: 'Twelve rubric rows, each scored as a conservative range with its evidence.',
    intro: 'The rubric splits the agent into three sub-scores and Big Data into three Vs, giving twelve rows. Evidence pointers are files a grader can open.',
    rows: [
      {
        id: 'spark',
        category: 'Spark Data Pipeline',
        component: 'Whole category',
        pointsPossible: 15,
        whatTheGraderLooksFor:
          'Spark, not only pandas, that ingests, cleans, enriches and validates data; re-runnable and idempotent; handles schema, nulls, duplicates and malformed records; output tables that serve the application.',
        evidence: 'pipelines/run_silver_gold.py:42-60,177-284; silver/01_silver_ohlcv.sql:1-19; silver/02_silver_ohlcv_quarantine.sql:1-10; gold/05_gold_model_features.sql:1-23; docs/proposal/row_counts_2026-10-05.tsv',
        evidenceStrength: 'partly-demonstrated',
        selfAssessedBand: { low: 9, high: 12 },
        bandReasoning:
          'Code meets most top-band descriptors: MERGE on stable keys, quarantine, null and range rules, and point-in-time checks that fail the build. Dated counts show it ran. No run logs are committed, and a clean rebuild depends on step order.',
        gap: 'Commit dated run logs, fix the rebuild order and show that a re-run leaves counts unchanged.',
        unverifiedItems: ['Spark execution logs'],
      },
      {
        id: 'api',
        category: 'Third-Party API Integration',
        component: 'Whole category',
        pointsPossible: 10,
        whatTheGraderLooksFor:
          'Real external data stored and used downstream, with secrets management, rate-limit handling, retries, malformed-response handling and validation. Simulated or hardcoded data loses credit.',
        evidence: 'etl/corporate_actions.py:208-290; pipelines/sec_rag_ingest.py:86-95,700-712,839-871; notebooks/refresh_bronze_options.py:385-399,662-681; notebooks/refresh_bronze_fed.py:194-215',
        evidenceStrength: 'partly-demonstrated',
        selfAssessedBand: { low: 6, high: 8 },
        bandReasoning:
          'Five providers feed stored, dated tables that features and retrieval use; no production path serves simulated or hardcoded data. Secrets, retries and rate limiting are strongest for SEC and corporate actions. No request logs are committed.',
        gap: 'Apply one retry and validation policy to every provider and commit redacted request and failure logs.',
        unverifiedItems: ['API request and error logs'],
      },
      {
        id: 'lakebase',
        category: 'Lakebase Data Model',
        component: 'Whole category',
        pointsPossible: 15,
        whatTheGraderLooksFor:
          'Clear core entities with primary keys and relationships; constraints that block duplicates and invalid writes; indexes, timestamps and audit fields; an application that actually reads and writes Lakebase.',
        evidence: 'db/migrations/001_operational_schema.sql:18-145; db/migrations/002_approvals_accounts.sql:23-45; db/migrations/005_agent_runtime.sql:15-38; db/lakebase.py:1-10; agent/tools_write.py:188-280',
        evidenceStrength: 'partly-demonstrated',
        selfAssessedBand: { low: 9, high: 12 },
        bandReasoning:
          'Versioned migrations define users, watchlists, notes, orders, approvals, executions, positions and agent actions with keys, foreign keys, unique and check constraints, indexes and timestamps. Applied state and live reads and writes cannot be re-checked offline.',
        gap: 'Document the model on one schema page and record applied migration versions with a write-then-read check.',
        unverifiedItems: ['Applied migrations', 'Live Lakebase connection'],
      },
      {
        id: 'agent-read',
        category: 'Action-Taking AI Agent',
        component: 'Retrieval and read tools',
        pointsPossible: 6,
        whatTheGraderLooksFor:
          'Tools that retrieve relevant structured and unstructured data accurately and within scope, combining sources such as Lakebase, Delta tables, APIs and vector search.',
        evidence: 'agent/contracts.py:203-209; agent/runtime.py:92-140; agent/tools_retrieval.py:127-168; api/services/hybrid_retriever.py:15-20; tests/rag/test_hybrid_retriever.py',
        evidenceStrength: 'partly-demonstrated',
        selfAssessedBand: { low: 3, high: 5 },
        bandReasoning:
          'Four bounded read tools combine Delta signals and features with hybrid vector and BM25 search over SEC text, filtered by acceptance time. Offline tests use fixtures; the one live retrieval is recorded only as README text.',
        gap: 'Record dated multi-source sessions with cited sources and add golden retrieval cases for the agent route.',
        unverifiedItems: ['Agent demo transcript'],
      },
      {
        id: 'agent-write',
        category: 'Action-Taking AI Agent',
        component: 'Write and action tools',
        pointsPossible: 8,
        whatTheGraderLooksFor:
          'Several reliable actions that save, update or delete Lakebase data, with validation, authorisation or confirmation, error handling and clear user feedback. A read-only chatbot does not qualify.',
        evidence: 'agent/runtime.py:141-156,487-598; agent/tools_write.py:188-280; api/schemas.py:131-148; frontend/src/api/client.ts:59-60',
        evidenceStrength: 'partly-demonstrated',
        selfAssessedBand: { low: 4, high: 6 },
        bandReasoning:
          'Two write tools save notes and add watchlist symbols, idempotently, behind request-scoped authorisation, role and demo checks, each with an audit row. The chat screen sends no write authorisation, so the UI cannot trigger them.',
        gap: 'Add an in-chat confirmation that sends write authorisation, show the saved record, and add an update or delete action.',
        unverifiedItems: ['Live write and read-back'],
      },
      {
        id: 'agent-quality',
        category: 'Action-Taking AI Agent',
        component: 'Quality and reasoning',
        pointsPossible: 6,
        whatTheGraderLooksFor:
          'Appropriate tool selection, answers grounded in retrieved data, explained actions, ambiguity handling, input validation, no unsupported claims, clear failure messages and accurate summaries of completed actions.',
        evidence: 'api/routes/agent_chat.py:1-19,41-101; agent/runtime.py:418-447,487-536; agent/contracts.py:147-201; tests/agent/test_runtime.py',
        evidenceStrength: 'partly-demonstrated',
        selfAssessedBand: { low: 2, high: 4 },
        bandReasoning:
          'The model chooses tools; code validates every proposal, refuses out-of-order or unbound writes, and returns named failure codes after one corrective retry. No transcript or evaluation of real-model reasoning is committed.',
        gap: 'Score a golden set of agent conversations, including ambiguous and adversarial prompts, and commit the transcripts.',
        unverifiedItems: ['Real-model transcripts'],
      },
      {
        id: 'analytics',
        category: 'Analytics Pipeline',
        component: 'Whole category',
        pointsPossible: 10,
        whatTheGraderLooksFor:
          'Demonstrated Lakebase Change Data Feed or Delta Live Tables feeding incremental, re-runnable analytics with useful metrics, monitoring and documented logic. A dashboard or summary table alone earns little.',
        evidence: 'db/migrations/004_analytics_outbox.sql:610-652; pipelines/lakebase_analytics.py:1-12,598-652; db/migrations/CDC.md; docs/rubric/PLAN.md:55-75',
        evidenceStrength: 'partly-demonstrated',
        selfAssessedBand: { low: 1, high: 4 },
        bandReasoning:
          'A transactional outbox and an idempotent Delta job compute agent-activity, watchlist, order-funnel and usage tables. The rubric names Change Data Feed or DLT; this design deliberately uses neither, so a strict grader may hold it in the lowest band.',
        gap: 'Ask the grader to rule on outbox equivalence, or adopt native Lakebase CDF once the instance supports it.',
        unverifiedItems: ['Change Data Feed or DLT configuration', 'Analytics run log'],
      },
      {
        id: 'frontend',
        category: 'Frontend and Core Workflow',
        component: 'Whole category',
        pointsPossible: 10,
        whatTheGraderLooksFor:
          'A clear interface to submit queries, view results and trigger agent actions, with writes reflected in the UI, loading, empty and error states, and confirmation for consequential actions.',
        evidence: 'frontend/src/App.tsx:116-152; frontend/src/screens/ResearchAgent.tsx; frontend/src/screens/OrderApprovalDrawer.tsx; frontend/src/screens/ResearchAgent.test.tsx',
        evidenceStrength: 'partly-demonstrated',
        selfAssessedBand: { low: 4, high: 7 },
        bandReasoning:
          'Market, options, filing, signal, agent, order-approval and health screens exist, with screen tests that include error states. Agent writes cannot start from the UI, and Activity Analytics and Strategy Lab are placeholders.',
        gap: 'Wire agent write confirmation and the analytics screen, then capture the flow in screenshots or the video.',
        unverifiedItems: ['Screenshots or demo transcript'],
      },
      {
        id: 'deployment',
        category: 'Deployed Application',
        component: 'Whole category',
        pointsPossible: 5,
        whatTheGraderLooksFor:
          'A stable, accessible deployment on Databricks Apps or Render with documented setup, environment configuration, secrets handling and reliable access. A local-only application does not earn full credit.',
        evidence: 'README.md:8,42-43; docs/DEPLOYMENT.md; resources/app.yml; render.yaml; docs/rubric/PLAN.md:33',
        evidenceStrength: 'unverified-needs-live-proof',
        selfAssessedBand: { low: 0, high: 3 },
        bandReasoning:
          'The README records a Databricks App verified healthy on 2026-10-05, and setup is documented. This snapshot claims no running service; if the app cannot be reached when graded, the rubric’s cannot-be-verified band of zero applies.',
        gap: 'Keep the app reachable through the grading window and commit a dated smoke-test result.',
        unverifiedItems: ['Deployment URL access'],
      },
      {
        id: 'volume',
        category: 'Big Data: Two of Three Vs',
        component: 'Volume',
        pointsPossible: 5,
        whatTheGraderLooksFor:
          'More than one million rows ingested and processed with a distributed workflow; full credit needs documented scale, partitioning, performance considerations and downstream use.',
        evidence: 'docs/BUSINESS_CASE.md:4,38-39; docs/proposal/row_counts_2026-10-05.tsv',
        evidenceStrength: 'demonstrated-in-repo',
        selfAssessedBand: { low: 3, high: 4 },
        bandReasoning:
          'Dated counts show 152,104,694 daily option rows and 23,420,557 Silver minute bars processed with Spark. Partitioning and performance are not documented, so the top band is not claimed.',
        gap: 'Document partitioning and run times from a dated Spark run.',
        unverifiedItems: ['Reproducible count query'],
      },
      {
        id: 'velocity',
        category: 'Big Data: Two of Three Vs',
        component: 'Velocity',
        pointsPossible: 5,
        whatTheGraderLooksFor:
          'Events processed in under one minute by a working incremental or streaming pipeline; full credit needs monitoring, checkpointing, recovery and measured latency.',
        evidence: 'bundles/streaming/README.md:1-10,26,58; README.md:47',
        evidenceStrength: 'not-demonstrated',
        selfAssessedBand: { low: 0, high: 1 },
        bandReasoning:
          'A continuous DLT bundle with a latency-metrics table exists, but it has never run, so no latency has been measured. All production ingestion is batch.',
        gap: 'Run the streaming bundle in an approved window and commit measured end-to-end latency with recovery evidence.',
        unverifiedItems: ['Measured processing latency'],
      },
      {
        id: 'variety',
        category: 'Big Data: Two of Three Vs',
        component: 'Variety',
        pointsPossible: 5,
        whatTheGraderLooksFor:
          'Unstructured data such as documents or text that is meaningfully transformed, embedded, indexed, searched or surfaced in the application workflow.',
        evidence: 'docs/BUSINESS_CASE.md:45; pipelines/build_sec_embeddings.py:4-5; api/services/hybrid_retriever.py:15-20; agent/tools_retrieval.py:127-168; frontend/src/screens/SecFilingExplorer.tsx',
        evidenceStrength: 'demonstrated-in-repo',
        selfAssessedBand: { low: 3, high: 5 },
        bandReasoning:
          'SEC filing text is chunked into 133,886 passages, embedded with BAAI/bge-small-en-v1.5, indexed for hybrid search and surfaced through the agent and the filing explorer. Retrieval quality rests on offline fixtures.',
        gap: 'Commit a dated retrieval evaluation on the real corpus and show cited passages in the demo.',
        unverifiedItems: ['Retrieval evaluation on the real corpus'],
      },
    ],
    byCategory: [
      {
        id: 'spark',
        category: 'Spark Data Pipeline',
        pointsPossible: 15,
        low: 9,
        high: 12,
        note: 'Functional band, reaching toward robust.',
      },
      {
        id: 'api',
        category: 'Third-Party API Integration',
        pointsPossible: 10,
        low: 6,
        high: 8,
        note: 'Working to reliably integrated.',
      },
      {
        id: 'lakebase',
        category: 'Lakebase Data Model',
        pointsPossible: 15,
        low: 9,
        high: 12,
        note: 'Appropriate relational schema; live use unverified.',
      },
      {
        id: 'agent',
        category: 'Action-Taking AI Agent',
        pointsPossible: 20,
        low: 9,
        high: 15,
        note: 'Sum of the three agent sub-scores; the required-agent cap is assessed separately below.',
      },
      {
        id: 'analytics',
        category: 'Analytics Pipeline',
        pointsPossible: 10,
        low: 1,
        high: 4,
        note: 'Outbox, not Change Data Feed or DLT.',
      },
      {
        id: 'frontend',
        category: 'Frontend and Core Workflow',
        pointsPossible: 10,
        low: 4,
        high: 7,
        note: 'Usable read workflow; agent writes not in the UI.',
      },
      {
        id: 'deployment',
        category: 'Deployed Application',
        pointsPossible: 5,
        low: 0,
        high: 3,
        note: 'Zero if unreachable when graded.',
      },
      {
        id: 'big-data',
        category: 'Big Data: Two of Three Vs',
        pointsPossible: 15,
        low: 6,
        high: 10,
        note: 'Volume and variety at a basic-to-partial level fall in the rubric’s 6–10 band; with velocity unmeasured, losing either V would cap the category at 5.',
      },
    ],
  },
  totals: {
    heading: 'The self-assessed range is 44 to 71 of 100, before any grader judgement.',
    possible: 100,
    selfAssessedLow: 44,
    selfAssessedHigh: 71,
    capApplies: false,
    capNote:
      'The 60-point cap applies only when the agent is missing or strictly read-only. Code gives the agent two authorised Lakebase write tools, and the README records a live note write, so the cap should not apply.',
    caveat:
      'A self-assessment against the rubric’s band descriptions, not a grade or a promised score. The ranges are judgements; unverified items can pull a grader’s score toward, or below, the low end.',
    swingFactors: [
      'Deployment: zero if the app cannot be reached when graded; up to 3 on the recorded deployment.',
      'Required-agent cap: if a grader can verify no agent write, for example by testing only the UI, the total is capped at 60.',
      'Analytics: the rubric names Change Data Feed or DLT; a strict reading holds the outbox design in the lowest band.',
      'Velocity: no latency has been measured, so the Big Data score rests on volume and variety alone.',
    ],
  },
  agent: {
    heading: 'The model proposes typed actions; deterministic code decides what executes.',
    intro:
      'The chat route calls a model-directed runtime; the earlier keyword dispatch has been removed. The model can use four read tools and propose two writes; order, approval and broker tools are never exposed to it.',
    capabilities: [
      {
        title: 'Retrieves filing evidence and market context.',
        text: 'Read tools return signals, market features, options features and hybrid SEC search results; filing text comes back as delimited evidence, never as instructions.',
        evidence: 'agent/contracts.py:203-209; agent/runtime.py:92-140,188-212',
      },
      {
        title: 'Saves research and watchlist entries in Lakebase.',
        text: 'Notes and watchlist additions run as parameterised transactions with an audit row; replaying a note with the same idempotency key returns the original note.',
        evidence: 'agent/runtime.py:141-156; agent/tools_write.py:188-280',
      },
      {
        title: 'Fails visibly instead of guessing.',
        text: 'Invalid output gets one corrective retry; then the run stops and returns a named reason such as malformed, write_not_authorized or role_denied.',
        evidence: 'agent/runtime.py:418-447; api/routes/agent_chat.py:8-15',
      },
      {
        title: 'Is evaluated offline, not yet on live sessions.',
        text: 'A RAG evaluation harness and golden fixtures test retrieval and answers; runtime tests cover injected instructions, malformed actions, authorisation and replay. No live-session evaluation is committed.',
        evidence: 'evals/rag_eval/__main__.py; tests/rag/test_rag_eval_round3.py; tests/agent/test_runtime.py',
      },
    ],
    safetyModel: {
      heading: 'Every agent write must clear five gates before it changes any data.',
      steps: [
        {
          title: 'Closed schema and allowlist.',
          text: 'Output must parse as one of four action types naming an allowed tool with strict arguments; unknown tools and extra fields are rejected.',
          enforcedIn: 'agent/contracts.py:147-225',
        },
        {
          title: 'Research before writing.',
          text: 'A write cannot be the first action and must target a symbol already researched; a note that cites evidence must cite chunk IDs from the same trace.',
          enforcedIn: 'agent/runtime.py:487-536',
        },
        {
          title: 'Request-scoped authorisation.',
          text: 'The request must name that exact write tool and carry an idempotency key; without it the write is refused.',
          enforcedIn: 'api/schemas.py:131-148; agent/runtime.py:538-566',
        },
        {
          title: 'Role and demo guards.',
          text: 'The user must hold the trader role, and public-demo mode refuses every write.',
          enforcedIn: 'agent/runtime.py:567-598; agent/tools_write.py:79',
        },
        {
          title: 'Audited execution.',
          text: 'Validated writes run through a closed registry, and each executed write inserts an agent_actions row in the same transaction as the change.',
          enforcedIn: 'agent/runtime.py:600-625; agent/tools_write.py:171-212',
        },
      ],
      caveats: [
        'The chat screen sends only the message, never write authorisation, so agent writes are reachable through the API, not the UI.',
        'The per-step runtime audit defaults to a no-op sink, so refused proposals leave no database record.',
        'The documented one-write-per-run budget is not enforced.',
        'Evidence binding applies only when SEC evidence was retrieved and the note cites IDs; a note may cite none.',
      ],
    },
  },
  demoScript: {
    heading: 'Seven offline steps let a grader check the evidence without a live service.',
    intro: 'Each step names what to open or run and what it proves. The tests use fixtures: they show behaviour in code, not live operation.',
    steps: [
      {
        order: 1,
        category: 'Spark Data Pipeline',
        show: 'The Silver/Gold orchestrator and its leakage tests.',
        proves: 'MERGE-based transforms with quarantine and point-in-time invariants that fail the build.',
        how: 'Open pipelines/run_silver_gold.py; run pytest -q tests/silver/test_silver_conversions.py tests/gold/test_pit_leakage.py',
      },
      {
        order: 2,
        category: 'Third-Party API Integration',
        show: 'Provider clients and their failure tests.',
        proves: 'Retries, rate limiting, authorisation errors and malformed-row rejection in production code paths.',
        how: 'Open etl/corporate_actions.py and pipelines/sec_rag_ingest.py; run pytest -q tests/bronze/test_corporate_actions.py',
      },
      {
        order: 3,
        category: 'Lakebase Data Model',
        show: 'The versioned migrations.',
        proves: 'Keys, foreign keys, unique and check constraints, indexes, timestamps and idempotency keys.',
        how: 'Open db/migrations/001_operational_schema.sql, 002_approvals_accounts.sql and 005_agent_runtime.sql',
      },
      {
        order: 4,
        category: 'Action-Taking AI Agent',
        show: 'The action contract and runtime tests.',
        proves: 'Proposals are validated; unauthorised, out-of-order and injected actions are refused; authorised writes execute.',
        how: 'Run pytest -q tests/agent/test_contracts.py tests/agent/test_runtime.py',
      },
      {
        order: 5,
        category: 'Analytics Pipeline',
        show: 'Outbox triggers and the Delta consumer tests.',
        proves: 'Same-transaction capture and replay-safe merging; it does not show Change Data Feed or DLT.',
        how: 'Run pytest -q tests/rubric/test_outbox_sql.py tests/rubric/test_lakebase_analytics.py',
      },
      {
        order: 6,
        category: 'Frontend and Core Workflow',
        show: 'The Research Agent screen tests.',
        proves: 'Tool calls, sources, saved-note confirmation and error states render correctly from fixture responses.',
        how: 'In frontend/, run npx vitest run src/screens/ResearchAgent.test.tsx',
      },
      {
        order: 7,
        category: 'Big Data and Deployed Application',
        show: 'Dated counts, retrieval tests, the architecture diagram and the README status table.',
        proves: 'Volume and variety evidence; deployment and latency remain claims that need live proof.',
        how: 'Run pytest -q tests/rag/test_hybrid_retriever.py; open docs/proposal/row_counts_2026-10-05.tsv, docs/proposal/architecture.png and README.md',
      },
    ],
  },
  gaps: {
    heading: 'Eight concrete actions would raise the score; none is done yet.',
    intro: 'Framed like the rubric’s suggestions for improvement. These are not promises, and no dates are attached.',
    items: [
      {
        id: 'deployment',
        category: 'Deployed Application',
        currentBand: '0–3',
        nextBand: '4',
        gap: 'No reachable deployment can be shown while the services are stopped.',
        concreteAction: 'With owner approval, keep the app and Lakebase running through the grading window and commit a dated smoke-test result.',
        status: 'planned',
      },
      {
        id: 'agent-write-ui',
        category: 'Action-Taking AI Agent',
        currentBand: '4–6 (write tools)',
        nextBand: '7–8',
        gap: 'Agent writes cannot be triggered or confirmed from the UI, and no update or delete action exists.',
        concreteAction: 'Add a confirm-before-write step in chat that sends write authorisation, show the saved record, and add a remove-from-watchlist tool.',
        status: 'not-started',
      },
      {
        id: 'analytics-mechanism',
        category: 'Analytics Pipeline',
        currentBand: '1–4',
        nextBand: '4–6',
        gap: 'The rubric credits Change Data Feed or DLT; the outbox is neither.',
        concreteAction: 'Seek a ruling on outbox equivalence, or adopt native Lakebase CDF once the instance supports it; never relabel the outbox as CDF.',
        status: 'planned',
      },
      {
        id: 'velocity',
        category: 'Big Data: Velocity',
        currentBand: '0–1',
        nextBand: '3–4',
        gap: 'No streaming run and no latency measurement exist.',
        concreteAction: 'Run the streaming bundle in an approved window and commit end-to-end latency, checkpoint and recovery evidence.',
        status: 'planned',
      },
      {
        id: 'agent-quality',
        category: 'Action-Taking AI Agent',
        currentBand: '2–4 (quality)',
        nextBand: '4–5',
        gap: 'No evaluation of live model sessions is committed.',
        concreteAction: 'Score a golden set of agent conversations, including ambiguous and adversarial prompts, and commit the transcripts.',
        status: 'not-started',
      },
      {
        id: 'spark-evidence',
        category: 'Spark Data Pipeline',
        currentBand: '9–12',
        nextBand: '13–15',
        gap: 'No committed run logs, and a clean rebuild depends on step order.',
        concreteAction: 'Build the tradable universe before the Silver steps that read it, and commit logs showing a re-run leaves counts unchanged.',
        status: 'not-started',
      },
      {
        id: 'api-consistency',
        category: 'Third-Party API Integration',
        currentBand: '6–8',
        nextBand: '9–10',
        gap: 'Retry and validation depth varies by provider, and no request logs are committed.',
        concreteAction: 'Share one retry, rate-limit and validation wrapper across providers and commit redacted run logs.',
        status: 'not-started',
      },
      {
        id: 'frontend-workflow',
        category: 'Frontend and Core Workflow',
        currentBand: '4–7',
        nextBand: '8–9',
        gap: 'Two placeholder screens, and no agent write from the UI.',
        concreteAction: 'Build the Activity Analytics screen on the existing analytics API, alongside the agent write confirmation above.',
        status: 'not-started',
      },
    ],
  },
  strengths: {
    heading: 'Four strengths a grader can verify directly in the code.',
    items: [
      {
        title: 'Point-in-time correctness is enforced at build time.',
        text: 'Every Gold feature carries an availability time, model snapshots join sources only as of the prediction time, and the orchestrator fails the build on any violating row.',
        evidence: 'gold/05_gold_model_features.sql:1-23; pipelines/run_silver_gold.py:177-284; tests/gold/test_pit_leakage.py',
      },
      {
        title: 'The agent cannot act on model output alone.',
        text: 'A closed action schema, an allowlist, request-scoped authorisation, and role and demo checks precede every write; broker tools are never exposed to the model.',
        evidence: 'agent/contracts.py:147-225; agent/runtime.py:487-598',
      },
      {
        title: 'Unstructured filings are searchable as of a date.',
        text: '133,886 SEC chunks are embedded and searched with hybrid BM25 and vector retrieval that excludes filings accepted after the as-of time.',
        evidence: 'docs/BUSINESS_CASE.md:45; api/services/hybrid_retriever.py:15-20,858-870',
      },
      {
        title: 'Operational changes reach Delta without dual writes.',
        text: 'Same-transaction outbox triggers on eight tables and a replay-safe Delta job turn Lakebase activity into analytics tables.',
        evidence: 'db/migrations/004_analytics_outbox.sql:610-652; pipelines/lakebase_analytics.py:598-652',
      },
    ],
  },
  evidenceGaps: {
    heading: 'The rubric’s evidence checklist, marked for this repository.',
    intro: 'The rubric treats missing evidence as unverified, not as proof of absence. Absent here means not committed to the repository.',
    items: [
      {
        item: 'Deployment URL',
        status: 'unverified',
        evidence: 'README.md:8,42',
        note: 'A URL and a 2026-10-05 health check are recorded; access depends on the app running when graded.',
      },
      {
        item: 'Spark execution logs',
        status: 'absent',
        evidence: 'docs/proposal/row_counts_2026-10-05.tsv',
        note: 'No run logs are committed; dated row counts are the only execution evidence.',
      },
      {
        item: 'Lakebase schema and connection code',
        status: 'verified-present',
        evidence: 'db/migrations/001_operational_schema.sql; db/lakebase.py:1-10',
        note: 'Migrations and an OAuth connection layer are committed; applied state is not.',
      },
      {
        item: 'Change Data Feed configuration',
        status: 'absent',
        evidence: 'docs/rubric/PLAN.md:55-65',
        note: 'The design chose a transactional outbox; native CDF is deferred until the instance supports it.',
      },
      {
        item: 'Dataset size',
        status: 'verified-present',
        evidence: 'docs/BUSINESS_CASE.md:3-4; docs/proposal/row_counts_2026-10-05.tsv:1',
        note: 'Two dated count snapshots are committed; neither can be re-queried offline.',
      },
      {
        item: 'Measured processing latency',
        status: 'absent',
        evidence: 'bundles/streaming/README.md:8-10,58',
        note: 'The streaming bundle defines latency metrics but has never run.',
      },
      {
        item: 'API request and error-handling code',
        status: 'verified-present',
        evidence: 'etl/corporate_actions.py:208-290; pipelines/sec_rag_ingest.py:700-712,839-871',
        note: 'Retry, rate-limit and validation code is committed; request logs are not.',
      },
      {
        item: 'Agent tool definitions',
        status: 'verified-present',
        evidence: 'agent/contracts.py:203-225',
        note: 'Four read tools and two write tools are defined in a closed contract.',
      },
      {
        item: 'Screenshots or demo transcript',
        status: 'absent',
        evidence: 'README.md:44',
        note: 'None are committed; the README describes one live agent run in text. The video can supply this.',
      },
    ],
  },
};
