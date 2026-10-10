import { INFRASTRUCTURE } from '../data/businessCase';
import {
  CrossLinks,
  EvidenceLine,
  FieldLabel,
  FUNNEL_STAGE_LABELS,
  PageIntro,
  ScrollRegion,
  SnapshotStrip,
  StatusBadge,
  type BusinessCaseScreenProps,
} from './businessCaseShared';

const FUTURE_STATUS_LABELS: Record<'planned' | 'built-not-deployed' | 'blocked-on-owner', string> = {
  planned: 'Planned',
  'built-not-deployed': 'Built, not deployed',
  'blocked-on-owner': 'Blocked on owner',
};

export function BusinessCaseInfrastructure({ onNavigate }: BusinessCaseScreenProps) {
  return (
    <div className="space-y-8">
      <PageIntro eyebrow={INFRASTRUCTURE.eyebrow} title={INFRASTRUCTURE.title} thought={INFRASTRUCTURE.governingThought} />

      <SnapshotStrip />

      <section
        aria-labelledby="bc-infra-flow"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Pipeline flow</p>
        <h2 id="bc-infra-flow" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          Pipeline flow
        </h2>
        <ol className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {INFRASTRUCTURE.flow.map((step, index) => (
            <li
              key={step.id}
              data-flow-id={step.id}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-fill)] text-xs font-bold text-[var(--accent-ink)]"
                >
                  {index + 1}
                </span>
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{step.label}</h3>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{step.role}</p>
              <EvidenceLine text={step.evidence} />
            </li>
          ))}
        </ol>
      </section>

      <section
        aria-labelledby="bc-infra-sources"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Sources</p>
        <h2 id="bc-infra-sources" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          External sources
        </h2>
        <ul className="mt-4 space-y-3">
          {INFRASTRUCTURE.sources.map((source) => (
            <li
              key={source.name}
              data-source={source.name}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">{source.name}</h3>
              <div className="mt-2">
                <FieldLabel>What it provides</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{source.whatItProvides}</p>
              </div>
              <div className="mt-2">
                <FieldLabel>How obtained</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{source.howObtained}</p>
              </div>
              <div className="mt-2">
                <FieldLabel>Lands in</FieldLabel>
                <p className="break-words text-xs text-[var(--text-muted)]" data-mono>{source.lands}</p>
              </div>
              <EvidenceLine text={source.evidence} />
            </li>
          ))}
        </ul>
      </section>

      {INFRASTRUCTURE.layers.map((layer) => (
        <section
          key={layer.id}
          id={`bc-infra-${layer.id}`}
          data-layer-id={layer.id}
          aria-labelledby={`bc-infra-${layer.id}-heading`}
          className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
        >
          <h2 id={`bc-infra-${layer.id}-heading`} className="text-lg font-semibold text-[var(--text-primary)]">
            {layer.heading}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{layer.conclusion}</p>
          <ul className="mt-4 space-y-3">
            {layer.items.map((item) => (
              <li
                key={item.name}
                data-layer-item={item.name}
                className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
              >
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{item.name}</h3>
                <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{item.what}</p>
                {item.rowsLabel && (
                  <div className="mt-2">
                    <FieldLabel>Rows</FieldLabel>
                    <p className="text-xs text-[var(--text-primary)]">{item.rowsLabel}</p>
                  </div>
                )}
                {item.asOf && (
                  <div className="mt-2">
                    <FieldLabel>As of</FieldLabel>
                    <p className="text-xs text-[var(--text-muted)]">{item.asOf}</p>
                  </div>
                )}
                <EvidenceLine text={item.evidence} />
              </li>
            ))}
          </ul>
        </section>
      ))}

      <section
        aria-labelledby="bc-infra-funnel"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Row-count funnel</p>
        <h2 id="bc-infra-funnel" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {INFRASTRUCTURE.funnel.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{INFRASTRUCTURE.funnel.intro}</p>
        <div className="mt-4">
          <ScrollRegion label="Row-count funnel">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--surface-raised)]">
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Stage</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Label</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Count</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">As of</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Note</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Source</th>
                </tr>
              </thead>
              <tbody>
                {INFRASTRUCTURE.funnel.steps.map((step) => (
                  <tr key={step.label} data-funnel-stage={step.stage} className="border-b border-[var(--border)] last:border-0">
                    <td className="px-4 py-3 text-xs font-medium text-[var(--text-primary)]">{FUNNEL_STAGE_LABELS[step.stage]}</td>
                    <td className="px-4 py-3 text-xs text-[var(--text-secondary)]">{step.label}</td>
                    <td className="px-4 py-3 text-xs font-medium text-[var(--text-primary)]">{step.count}</td>
                    <td className="px-4 py-3 text-xs text-[var(--text-muted)]">{step.asOf}</td>
                    <td className="px-4 py-3 text-xs leading-relaxed text-[var(--text-secondary)]">{step.note}</td>
                    <td className="px-4 py-3 break-words text-xs text-[var(--text-muted)]" data-mono>{step.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollRegion>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-[var(--text-muted)]">{INFRASTRUCTURE.funnel.caveat}</p>
      </section>

      <section
        aria-labelledby="bc-infra-why-not-silver"
        className="rounded-[var(--radius-lg)] border-2 border-[var(--border-strong)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--warning)]">Why not everything is in Silver</p>
        <h2 id="bc-infra-why-not-silver" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {INFRASTRUCTURE.whyNotEverythingIsInSilver.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
          {INFRASTRUCTURE.whyNotEverythingIsInSilver.text}
        </p>
        <ul className="mt-3 space-y-2">
          {INFRASTRUCTURE.whyNotEverythingIsInSilver.points.map((point, index) => (
            <li
              key={index}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3"
            >
              <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{point.text}</p>
              <EvidenceLine text={point.evidence} />
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="bc-infra-future"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Future improvements</p>
        <h2 id="bc-infra-future" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {INFRASTRUCTURE.future.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{INFRASTRUCTURE.future.intro}</p>
        <ul className="mt-4 space-y-3">
          {INFRASTRUCTURE.future.items.map((item) => (
            <li
              key={item.id}
              data-future-id={item.id}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{item.title}</h3>
                <StatusBadge code={item.status} label={FUTURE_STATUS_LABELS[item.status]} />
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{item.text}</p>
              <div className="mt-2">
                <FieldLabel>Exists today</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{item.existsToday}</p>
              </div>
              <div className="mt-2">
                <FieldLabel>Still to do</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{item.stillToDo}</p>
              </div>
              <EvidenceLine text={item.evidence} />
            </li>
          ))}
        </ul>
      </section>

      <CrossLinks current="infrastructure" onNavigate={onNavigate} />
    </div>
  );
}