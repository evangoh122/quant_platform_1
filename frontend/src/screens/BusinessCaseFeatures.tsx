import { FEATURES, NEXT_APPROACH, type NextApproach } from '../data/businessCase';
import { Table, type Column } from '../components/Table';
import {
  CrossLinks,
  EvidenceLine,
  FieldLabel,
  PLANNED_STATUS_LABELS,
  ROADMAP_STATUS_LABELS,
  PageIntro,
  ScrollRegion,
  SnapshotStrip,
  StatusBadge,
  type BusinessCaseScreenProps,
} from './businessCaseShared';

type StudyItem = NextApproach['studies']['items'][number];

const STUDY_COLUMNS: Column<StudyItem>[] = [
  {
    key: 'name',
    header: 'Study',
    render: (study) => <span className="text-sm font-medium text-[var(--text-primary)]">{study.name}</span>,
  },
  {
    key: 'usedFor',
    header: 'Used for',
    render: (study) => <span className="text-xs leading-relaxed text-[var(--text-secondary)]">{study.usedFor}</span>,
  },
  {
    key: 'inCodeToday',
    header: 'In code today',
    render: (study) => <span className="text-xs leading-relaxed text-[var(--text-secondary)]">{study.inCodeToday}</span>,
  },
  {
    key: 'citedIn',
    header: 'Cited in',
    render: (study) => (
      <span className="break-words text-xs text-[var(--text-muted)]" data-mono>
        {study.citedIn}
      </span>
    ),
  },
];

function roadmapStepOrder(stepId: string): number | undefined {
  return NEXT_APPROACH.whatWeIntendToDo.steps.find((candidate) => candidate.id === stepId)?.order;
}

export function BusinessCaseFeatures({ onNavigate }: BusinessCaseScreenProps) {
  return (
    <div className="space-y-8">
      <PageIntro eyebrow={FEATURES.eyebrow} title={FEATURES.title} thought={FEATURES.governingThought} />

      <SnapshotStrip />

      <section
        aria-labelledby="bc-available-today"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Available today</p>
        <h2 id="bc-available-today" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          Available today
        </h2>
        <ul className="mt-4 space-y-3">
          {FEATURES.available.map((item) => (
            <li
              key={item.id}
              data-item-id={item.id}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">{item.heading}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{item.text}</p>
              <EvidenceLine text={item.evidence} />
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="bc-planned"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Planned / not done</p>
        <h2 id="bc-planned" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          Planned / not done
        </h2>
        <ul className="mt-4 space-y-3">
          {FEATURES.planned.map((item) => (
            <li
              key={item.id}
              data-item-id={item.id}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{item.heading}</h3>
                <StatusBadge code={item.status} label={PLANNED_STATUS_LABELS[item.status]} />
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{item.text}</p>
              <div className="mt-2">
                <FieldLabel>Why</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-primary)]">{item.why}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="bc-roadmap"
        data-roadmap
        className="rounded-[var(--radius-lg)] border-2 border-[var(--border-strong)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">{NEXT_APPROACH.eyebrow}</p>
        <h2 id="bc-roadmap" className="mt-1 text-xl font-bold text-[var(--text-primary)]">
          {NEXT_APPROACH.title}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{NEXT_APPROACH.governingThought}</p>

        <div
          data-roadmap-banner
          role="status"
          className="mt-4 rounded-[var(--radius-md)] border-2 border-[var(--warning)] bg-warning-dim p-4"
        >
          <p className="flex items-center gap-2 text-base font-semibold text-warning-text">
            <span aria-hidden="true">&#9888;</span>
            {NEXT_APPROACH.statusLabel}
          </p>
          <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{NEXT_APPROACH.statusNote}</p>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <div
            data-insteadof="from"
            className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
          >
            <FieldLabel>From</FieldLabel>
            <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{NEXT_APPROACH.insteadOf.from}</p>
          </div>
          <div
            data-insteadof="to"
            className="rounded-[var(--radius-md)] border border-[var(--accent)] bg-[var(--accent-dim)] p-4"
          >
            <FieldLabel>To</FieldLabel>
            <p className="text-sm leading-relaxed text-[var(--text-primary)]">{NEXT_APPROACH.insteadOf.to}</p>
          </div>
        </div>

        <section aria-labelledby="bc-what-exists-today" className="mt-6">
          <h3 id="bc-what-exists-today" className="text-base font-semibold text-[var(--text-primary)]">
            {NEXT_APPROACH.whatExistsToday.heading}
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
            {NEXT_APPROACH.whatExistsToday.intro}
          </p>
          <ul className="mt-3 space-y-3">
            {NEXT_APPROACH.whatExistsToday.items.map((item) => (
              <li
                key={item.title}
                className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
              >
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">{item.title}</h4>
                <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{item.text}</p>
                <EvidenceLine text={item.evidence} />
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="bc-what-we-intend" className="mt-6">
          <h3 id="bc-what-we-intend" className="text-base font-semibold text-[var(--text-primary)]">
            {NEXT_APPROACH.whatWeIntendToDo.heading}
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
            {NEXT_APPROACH.whatWeIntendToDo.intro}
          </p>
          <div className="mt-3 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3">
            <FieldLabel>Ordering logic</FieldLabel>
            <p className="text-sm leading-relaxed text-[var(--text-primary)]">
              {NEXT_APPROACH.whatWeIntendToDo.orderingLogic}
            </p>
          </div>
          <ol className="mt-4 space-y-4">
            {NEXT_APPROACH.whatWeIntendToDo.steps.map((step) => (
              <li
                key={step.id}
                data-step-id={step.id}
                data-step-order={step.order}
                className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                    Step {step.order}: {step.title}
                  </h4>
                  <StatusBadge code={step.status} label={ROADMAP_STATUS_LABELS[step.status]} />
                </div>
                <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{step.text}</p>
                <div className="mt-2">
                  <FieldLabel>Why it matters</FieldLabel>
                  <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{step.whyItMatters}</p>
                </div>
                <div className="mt-2">
                  <FieldLabel>Proposed artifact</FieldLabel>
                  <p className="text-sm leading-relaxed text-[var(--text-primary)]">{step.proposedArtifact}</p>
                </div>
                <div className="mt-2">
                  <FieldLabel>Acceptance</FieldLabel>
                  <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{step.acceptance}</p>
                </div>
                {step.dependsOn.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {step.dependsOn.map((dependencyId) => (
                      <li key={dependencyId} data-depends-on={dependencyId}>
                        <span className="text-xs font-medium text-[var(--accent)]">
                          Depends on step {roadmapStepOrder(dependencyId)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-2">
                  <FieldLabel>Exists today</FieldLabel>
                  <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{step.existsToday}</p>
                </div>
                <div className="mt-2">
                  <FieldLabel>Still to do</FieldLabel>
                  <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{step.stillToDo}</p>
                </div>
                <EvidenceLine text={step.evidence} />
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="bc-studies" className="mt-6">
          <h3 id="bc-studies" className="text-base font-semibold text-[var(--text-primary)]">
            {NEXT_APPROACH.studies.heading}
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{NEXT_APPROACH.studies.intro}</p>
          <div className="mt-3">
            <ScrollRegion label="Roadmap studies">
              <Table columns={STUDY_COLUMNS} rows={NEXT_APPROACH.studies.items} rowKey={(study) => study.name} />
            </ScrollRegion>
          </div>
        </section>

        <section aria-labelledby="bc-how-judged" className="mt-6">
          <h3 id="bc-how-judged" className="text-base font-semibold text-[var(--text-primary)]">
            {NEXT_APPROACH.howWeWillJudgeIt.heading}
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
            {NEXT_APPROACH.howWeWillJudgeIt.intro}
          </p>
          <ul className="mt-3 list-disc space-y-2 pl-5">
            {NEXT_APPROACH.howWeWillJudgeIt.items.map((item) => (
              <li key={item} className="text-sm leading-relaxed text-[var(--text-secondary)]">
                {item}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="bc-honest-outlook" className="mt-6">
          <h3 id="bc-honest-outlook" className="text-base font-semibold text-[var(--text-primary)]">
            {NEXT_APPROACH.honestOutlook.heading}
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
            {NEXT_APPROACH.honestOutlook.text}
          </p>
        </section>
      </section>

      <CrossLinks current="features" onNavigate={onNavigate} />
    </div>
  );
}
