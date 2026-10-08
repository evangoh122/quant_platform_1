import type { ReactNode } from 'react';

interface PlatformOverviewProps {
  onNavigate: (id: string) => void;
}

const SNAPSHOT_DATE = '2026-10-05';

interface EvidenceCardProps {
  label: string;
  value: string;
  detail?: string;
}

function EvidenceCard({ label, value, detail }: EvidenceCardProps) {
  return (
    <div data-evidence-card className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
      <p className="text-2xl font-bold text-slate-900 dark:text-slate-50">{value}</p>
      <p className="mt-1 text-sm font-medium text-slate-600 dark:text-slate-300">{label}</p>
      {detail && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail}</p>
      )}
      <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
        Verified snapshot: {SNAPSHOT_DATE}
      </p>
    </div>
  );
}

interface RubricCardProps {
  title: string;
  description: string;
  target: string;
  onNavigate: (id: string) => void;
}

function RubricCard({ title, description, target, onNavigate }: RubricCardProps) {
  return (
    <button
      type="button"
      onClick={() => onNavigate(target)}
      className="rounded-lg border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-[var(--accent)] hover:shadow-md dark:border-slate-700 dark:bg-slate-900"
    >
      <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{description}</p>
      <p className="mt-2 text-xs font-medium text-[var(--accent)]">View &rarr;</p>
    </button>
  );
}

interface StepperStageProps {
  label: string;
  isLast: boolean;
}

function StepperStage({ label, isLast }: StepperStageProps) {
  return (
    <li className="flex items-center gap-2">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-bold text-white">
        &#10003;
      </span>
      <span className="text-sm text-slate-700 dark:text-slate-200">{label}</span>
      {!isLast && (
        <span className="mx-1 hidden h-px flex-1 bg-slate-300 dark:bg-slate-600 sm:block" aria-hidden="true" />
      )}
    </li>
  );
}

const PIPELINE_STAGES = [
  'External APIs',
  'Spark ingestion',
  'Delta bronze/silver/gold',
  'AI retrieval',
  'Lakebase action',
  'Delta activity analytics',
];

const RUBRIC_CARDS: { title: string; description: string; target: string }[] = [
  { title: 'Market Explorer', description: 'OHLCV features, price data, and volume analytics for any symbol.', target: 'market' },
  { title: 'Options Analytics', description: 'Put/call ratios, IV surfaces, skew, and term structure.', target: 'options' },
  { title: 'SEC Research', description: 'Embedding chunks from SEC filings with semantic search.', target: 'sec' },
  { title: 'AI Research Agent', description: 'Natural-language Q&A grounded in market data and SEC filings.', target: 'agent' },
  { title: 'Signal Explorer', description: 'Baseline logistic-regression signals with no edge claimed.', target: 'signals' },
  { title: 'Paper Portfolio', description: 'Simulated positions and order tracking on Lakebase.', target: 'portfolio' },
  { title: 'System Health', description: 'Dependency status, circuit breakers, and trace events.', target: 'health' },
  { title: 'Architecture & Tests', description: 'Pipeline diagram, safety model, and verified test groups.', target: 'architecture' },
];

export function PlatformOverview({ onNavigate }: PlatformOverviewProps) {
  return (
    <div className="space-y-8">
      <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">
          Quant Research Platform
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          Market and regulatory records transformed through Spark, searched through
          a governed AI agent, and audited through Lakebase and Delta analytics.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => onNavigate('agent')}
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
          >
            Ask the Research Agent
          </button>
          <button
            type="button"
            onClick={() => onNavigate('market')}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            Explore Market Data
          </button>
          <button
            type="button"
            onClick={() => onNavigate('architecture')}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            View Architecture &amp; Tests
          </button>
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100">
          Verified Evidence
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <EvidenceCard label="Market & regulatory records" value="287M+" detail="Across Massive, SEC, CFTC, and FRED sources" />
          <EvidenceCard label="Options records" value="152.1M" detail="Put/call volume, IV surfaces, and OI concentration" />
          <EvidenceCard label="SEC embedding chunks" value="10,720" detail="Semantic search over 10-K, 10-Q, 8-K, and S-1 filings" />
          <EvidenceCard label="Third-party providers" value="4" detail="Massive, SEC EDGAR, CFTC, and FRED" />
          <EvidenceCard label="Operational model" value="Lakebase" detail="Postgres-backed write path for notes, watchlists, orders" />
          <EvidenceCard label="Data pipeline" value="Spark bronze/silver/gold" detail="Delta Lake medallion architecture with DLT" />
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100">
          Platform Pipeline
        </h2>
        <nav aria-label="Pipeline stages">
          <ol className="flex flex-wrap items-center gap-3">
            {PIPELINE_STAGES.map((stage, i) => (
              <StepperStage key={stage} label={stage} isLast={i === PIPELINE_STAGES.length - 1} />
            ))}
          </ol>
        </nav>
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100">
          Explore the Platform
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {RUBRIC_CARDS.map((card) => (
            <RubricCard
              key={card.target}
              title={card.title}
              description={card.description}
              target={card.target}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      </section>
    </div>
  );
}