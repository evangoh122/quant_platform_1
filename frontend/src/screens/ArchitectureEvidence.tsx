const SNAPSHOT_DATE = '2026-10-05';

const PIPELINE_TECH_NODES = [
  'Massive',
  'SEC',
  'CFTC',
  'FRED',
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
  'Baseline signals only — model baseline-logreg-v0-2026-10-05 with hold-out AUC 0.47; no validated trading edge claimed.',
  'DLT (Delta Live Tables) pipeline built but not deployed to production.',
  'Paper broker scaffold — no live brokerage integration.',
  'Analytics require the Lakebase analytics refresh run to populate materialized views.',
];

export function ArchitectureEvidence() {
  return (
    <div className="space-y-8">
      <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">
          Architecture &amp; Tests
        </h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Verified architecture, safety model, and test evidence for the quant research platform.
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-800 dark:text-slate-100">
          Business Workflow
        </h2>
        <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
          <ol className="space-y-2 text-sm text-slate-700 dark:text-slate-200" aria-label="Business workflow steps">
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-white">1</span>
              <span>User asks a research question</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-white">2</span>
              <span>Governed retrieval from SEC filings, market data, and options analytics</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-white">3</span>
              <span>Grounded response with source citations and tool-call evidence</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-white">4</span>
              <span>Saved research note to Lakebase</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-white">5</span>
              <span>Lakebase audit trail</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-[10px] font-bold text-white">6</span>
              <span>Delta analytics materialisation</span>
            </li>
          </ol>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-800 dark:text-slate-100">
          Technical Architecture
        </h2>
        <div
          data-tour="pipeline-nodes"
          className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
          role="img"
          aria-label="Technical architecture diagram showing the data flow from external sources through processing to the application layer"
        >
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
            Responsive technical diagram &mdash; data flows left to right, top to bottom on small screens.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {PIPELINE_TECH_NODES.map((node, i) => (
              <span key={node} className="flex items-center gap-1">
                <span className="inline-block rounded-md border border-slate-300 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200">
                  {node}
                </span>
                {i < PIPELINE_TECH_NODES.length - 1 && (
                  <span className="text-slate-400" aria-hidden="true">&rarr;</span>
                )}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-800 dark:text-slate-100">
          Deterministic Safety Model
        </h2>
        <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
            The LLM never executes writes directly. Every write follows this deterministic chain:
          </p>
          <ol className="space-y-2" aria-label="Safety model steps">
            {SAFETY_MODEL_STEPS.map((step, i) => (
              <li key={step} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-slate-300 bg-slate-50 text-[10px] font-bold text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {i + 1}
                </span>
                <span>{step}</span>
                {i < SAFETY_MODEL_STEPS.length - 1 && (
                  <span className="text-slate-400" aria-hidden="true">&rarr;</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-800 dark:text-slate-100">
          Verified Test Groups
        </h2>
        <div className="space-y-3">
          {TEST_GROUPS.map((group) => (
            <div
              key={group.name}
              className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
            >
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                {group.name}
              </p>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                {group.description}
              </p>
              <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
                Commit: {group.commit} &middot; Date: {group.date}
              </p>
            </div>
          ))}
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Commit SHAs and dates are placeholders &mdash; to be filled after test runs on the build branch.
          </p>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-slate-800 dark:text-slate-100">
          Known Limitations
        </h2>
        <div
          data-tour="provenance"
          className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950"
        >
          <ul className="space-y-2 text-sm text-amber-800 dark:text-amber-200" aria-label="Known limitations">
            {LIMITATIONS.map((limitation) => (
              <li key={limitation} className="flex items-start gap-2">
                <span className="mt-1 text-amber-500" aria-hidden="true">&#9888;</span>
                <span>{limitation}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}