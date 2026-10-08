const SNAPSHOT_DATE = '2026-10-05';

const PIPELINE_TECH_NODES = [
  'Upstream providers (Massive, SEC, CFTC, FRED)',
  'Spark',
  'Delta bronze/silver/gold',
  'FastAPI',
  'React',
  'AI agent',
  'Lakebase',
  'analytics_outbox',
  'Spark analytics',
  'Delta analytics',
];

const SAFETY_MODEL_STEPS = [
  'LLM proposes',
  'Typed schema validates',
  'Allowlist check',
  'Write authorisation',
  'Deterministic execution',
  'Audit record',
];

const TEST_GROUPS = [
  {
    name: 'Contract tests',
    description: 'API schema and response-shape validation',
    commit: '<pending>',
    date: '<pending>',
  },
  {
    name: 'Integration tests',
    description: 'End-to-end agent chat, market, signals, and portfolio flows',
    commit: '<pending>',
    date: '<pending>',
  },
  {
    name: 'UI component tests',
    description: 'Layout, navigation, tours, and screen rendering',
    commit: '<pending>',
    date: '<pending>',
  },
  {
    name: 'Retrieval tests',
    description: 'SEC filing search, vector retrieval, and grounding verification',
    commit: '<pending>',
    date: '<pending>',
  },
];

const LIMITATIONS = [
  'Baseline signals only: a 1-trading-day logistic-regression baseline used to demonstrate the pipeline — no validated trading edge claimed.',
  'DLT (Delta Live Tables) pipeline built but not deployed to production.',
  'Paper broker scaffold — no live brokerage integration.',
  'Analytics require the Lakebase analytics refresh run to populate materialized views.',
];

export function ArchitectureEvidence() {
  return (
    <div className="space-y-8">
      <section className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-6">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          Architecture &amp; Tests
        </h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          Verified architecture, safety model, and test evidence for the quant research platform.
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-[var(--text-primary)]">
          Business Workflow
        </h2>
        <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
          <ol className="space-y-2 text-sm text-[var(--text-secondary)]" aria-label="Business workflow steps">
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent-fill)] text-[10px] font-bold text-[var(--accent-ink)]">1</span>
              <span>User asks a research question</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent-fill)] text-[10px] font-bold text-[var(--accent-ink)]">2</span>
              <span>Governed retrieval from SEC filings, market data, and options analytics</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent-fill)] text-[10px] font-bold text-[var(--accent-ink)]">3</span>
              <span>Grounded response with source citations and tool-call evidence</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent-fill)] text-[10px] font-bold text-[var(--accent-ink)]">4</span>
              <span>Optional: save research note to Lakebase (when agent returns a note_id)</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent-fill)] text-[10px] font-bold text-[var(--accent-ink)]">5</span>
              <span>Lakebase audit trail</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent-fill)] text-[10px] font-bold text-[var(--accent-ink)]">6</span>
              <span>Delta analytics materialisation</span>
            </li>
          </ol>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-[var(--text-primary)]">
          Technical Architecture
        </h2>
        <div
          data-tour="pipeline-nodes"
          className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-4"
        >
          <h3 className="mb-3 text-sm font-semibold text-[var(--text-secondary)]">
            Pipeline data flow
          </h3>
          <ol className="flex flex-wrap items-center gap-2" aria-label="Technical architecture pipeline nodes">
            {PIPELINE_TECH_NODES.map((node, i) => (
              <li key={node} className="flex items-center gap-1">
                <span className="inline-block rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-xs font-medium text-[var(--text-primary)]">
                  {node}
                </span>
                {i < PIPELINE_TECH_NODES.length - 1 && (
                  <span className="text-[var(--text-muted)]" aria-hidden="true">&rarr;</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-[var(--text-primary)]">
          Deterministic Safety Model
        </h2>
        <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
          <p className="mb-3 text-xs text-[var(--text-muted)]">
            The LLM never executes writes directly. Every write follows this deterministic chain:
          </p>
          <ol className="space-y-2" aria-label="Safety model steps">
            {SAFETY_MODEL_STEPS.map((step, i) => (
              <li key={step} className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--surface)] text-[10px] font-bold text-[var(--text-muted)]">
                  {i + 1}
                </span>
                <span>{step}</span>
                {i < SAFETY_MODEL_STEPS.length - 1 && (
                  <span className="text-[var(--text-muted)]" aria-hidden="true">&rarr;</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-[var(--text-primary)]">
          Verified Test Groups
        </h2>
        <div className="space-y-3">
          {TEST_GROUPS.map((group) => (
            <div
              key={group.name}
              className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-4"
            >
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {group.name}
              </p>
              <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                {group.description}
              </p>
              <p className="mt-2 text-xs text-[var(--text-muted)]">
                Commit: {group.commit} &middot; Date: {group.date}
              </p>
            </div>
          ))}
          <p className="text-xs text-[var(--text-muted)]">
            Commit SHAs and dates are placeholders &mdash; to be filled after test runs on the build branch.
          </p>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-[var(--text-primary)]">
          Known Limitations
        </h2>
        <div
          data-tour="provenance"
          className="rounded-[var(--radius-lg)] border border-[var(--warning)] bg-[var(--warning)]/10 p-4"
        >
          <ul className="space-y-2 text-sm text-[var(--warning)]" aria-label="Known limitations">
            {LIMITATIONS.map((limitation) => (
              <li key={limitation} className="flex items-start gap-2">
                <span className="mt-1" aria-hidden="true">&#9888;</span>
                <span>{limitation}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}