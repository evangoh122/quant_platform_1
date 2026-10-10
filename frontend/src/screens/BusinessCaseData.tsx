import { DATA } from '../data/businessCase';
import { StatTile } from '../components/StatTile';
import {
  CrossLinks,
  DATA_STATUS_LABELS,
  FieldLabel,
  PageIntro,
  SnapshotStrip,
  StatusBadge,
  type BusinessCaseScreenProps,
} from './businessCaseShared';

export function BusinessCaseData({ onNavigate }: BusinessCaseScreenProps) {
  return (
    <div className="space-y-8">
      <PageIntro eyebrow={DATA.eyebrow} title={DATA.title} thought={DATA.governingThought} />

      <SnapshotStrip />

      <section aria-label="Snapshot figures" data-snapshot-figures>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">Snapshot figures</h2>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {DATA.tiles.map((tile) => (
            <StatTile key={tile.label} label={tile.label} value={tile.value} hint={tile.note} />
          ))}
        </div>
      </section>

      {DATA.groups.map((group) => (
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
            {group.rows.map((row) => (
              <li
                key={row.name}
                data-row={row.name}
                className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h3 className="text-sm font-semibold text-[var(--text-primary)]">{row.name}</h3>
                  <StatusBadge code={row.status} label={DATA_STATUS_LABELS[row.status]} />
                </div>
                <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{row.what}</p>
                {row.size && (
                  <div className="mt-2">
                    <FieldLabel>Size</FieldLabel>
                    <p className="text-xs text-[var(--text-primary)]">{row.size}</p>
                  </div>
                )}
                {row.note && (
                  <div className="mt-2">
                    <FieldLabel>Note</FieldLabel>
                    <p className="text-xs leading-relaxed text-[var(--text-muted)]">{row.note}</p>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}

      <CrossLinks current="data" onNavigate={onNavigate} />
    </div>
  );
}
