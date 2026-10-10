import { CONTROLS } from '../data/businessCase';
import {
  CrossLinks,
  FieldLabel,
  PageIntro,
  SnapshotStrip,
  type BusinessCaseScreenProps,
} from './businessCaseShared';

export function BusinessCaseControls({ onNavigate }: BusinessCaseScreenProps) {
  return (
    <div className="space-y-8">
      <PageIntro eyebrow={CONTROLS.eyebrow} title={CONTROLS.title} thought={CONTROLS.governingThought} />

      <SnapshotStrip />

      {CONTROLS.groups.map((group) => (
        <section
          key={group.id}
          id={`bc-${group.id}`}
          data-group-id={group.id}
          aria-labelledby={`bc-${group.id}-heading`}
          className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
        >
          <h2 id={`bc-${group.id}-heading`} className="text-lg font-semibold text-[var(--text-primary)]">
            {group.heading}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{group.conclusion}</p>
          <ul className="mt-4 space-y-3">
            {group.items.map((item) => (
              <li
                key={item.control}
                data-control={item.control}
                className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
              >
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{item.control}</h3>
                <div className="mt-2">
                  <FieldLabel>How</FieldLabel>
                  <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{item.how}</p>
                </div>
                <div className="mt-2">
                  <FieldLabel>Enforced in</FieldLabel>
                  <p className="break-words text-xs text-[var(--text-muted)]" data-mono>
                    {item.enforcedIn}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <section
        id="bc-known-limitations"
        data-group-id="known-limitations"
        aria-labelledby="bc-known-limitations-heading"
        className="rounded-[var(--radius-lg)] border-2 border-[var(--border-strong)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--warning)]">Known limitations</p>
        <h2 id="bc-known-limitations-heading" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {CONTROLS.limitations.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{CONTROLS.limitations.intro}</p>
        <ul className="mt-4 space-y-3">
          {CONTROLS.limitations.items.map((entry) => (
            <li
              key={entry.limit}
              data-limitation={entry.limit}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <h3 className="flex items-start gap-2 text-sm font-semibold text-[var(--text-primary)]">
                <span aria-hidden="true" className="mt-0.5 text-[var(--warning)]">
                  &#9888;
                </span>
                {entry.limit}
              </h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{entry.impact}</p>
            </li>
          ))}
        </ul>
      </section>

      <CrossLinks current="controls" onNavigate={onNavigate} />
    </div>
  );
}
