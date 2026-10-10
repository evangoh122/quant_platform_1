import { EXECUTIVE_SUMMARY, KEY_LINE, OVERVIEW } from '../data/businessCase';
import {
  CrossLinks,
  FieldLabel,
  PAGE_LABELS,
  PageIntro,
  SnapshotStrip,
  screenIdForPage,
  type BusinessCaseScreenProps,
} from './businessCaseShared';

const SCQA_ORDER = [
  { key: 'situation', label: 'Situation', text: EXECUTIVE_SUMMARY.situation },
  { key: 'complication', label: 'Complication', text: EXECUTIVE_SUMMARY.complication },
  { key: 'question', label: 'Question', text: EXECUTIVE_SUMMARY.question },
  { key: 'answer', label: 'Answer', text: EXECUTIVE_SUMMARY.answer },
] as const;

export function BusinessCaseOverview({ onNavigate }: BusinessCaseScreenProps) {
  return (
    <div className="space-y-8">
      <PageIntro eyebrow={OVERVIEW.eyebrow} title={OVERVIEW.title} thought={OVERVIEW.governingThought} />

      <SnapshotStrip />

      <section
        aria-labelledby="bc-executive-summary"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Executive summary</p>
        <h2 id="bc-executive-summary" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {EXECUTIVE_SUMMARY.heading}
        </h2>
        <div className="mt-4 space-y-3">
          {SCQA_ORDER.map((part) => (
            <section
              key={part.key}
              data-scqa-part={part.key}
              data-emphasis={part.key === 'answer' ? 'strong' : 'standard'}
              aria-label={part.label}
              className={
                part.key === 'answer'
                  ? 'rounded-[var(--radius-md)] border-l-4 border-[var(--accent)] bg-[var(--accent-dim)] p-4'
                  : 'rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4'
              }
            >
              <h3
                className={
                  part.key === 'answer'
                    ? 'text-base font-semibold text-[var(--accent-bright)]'
                    : 'text-sm font-semibold text-[var(--text-primary)]'
                }
              >
                {part.label}
              </h3>
              <p
                className={
                  part.key === 'answer'
                    ? 'mt-2 text-base leading-relaxed text-[var(--text-primary)]'
                    : 'mt-2 text-sm leading-relaxed text-[var(--text-secondary)]'
                }
              >
                {part.text}
              </p>
            </section>
          ))}
        </div>
      </section>

      <section
        aria-labelledby="bc-key-line"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Key line</p>
        <h2 id="bc-key-line" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          Key line
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{KEY_LINE.governingThought}</p>
        <div className="mt-3 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3">
          <FieldLabel>Ordering logic</FieldLabel>
          <p className="text-sm text-[var(--text-primary)]">{KEY_LINE.orderingLogic}</p>
        </div>
        <ul className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {KEY_LINE.arguments.map((arg) => (
            <li key={arg.id}>
              <button
                type="button"
                data-argument-id={arg.id}
                data-argument-page={arg.page}
                onClick={() => onNavigate(screenIdForPage(arg.page))}
                className="flex h-full w-full flex-col gap-2 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] p-4 text-left transition hover:border-[var(--accent)] hover:bg-[var(--surface-raised)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
              >
                <span className="block text-sm font-semibold text-[var(--text-primary)]">{arg.claim}</span>
                <span className="block text-xs leading-relaxed text-[var(--text-secondary)]">{arg.proof}</span>
                <span className="mt-auto block pt-2 text-xs font-medium text-[var(--accent)]">
                  View {PAGE_LABELS[arg.page]} &rarr;
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="bc-users" className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
        <h2 id="bc-users" className="text-lg font-semibold text-[var(--text-primary)]">
          {OVERVIEW.users.heading}
        </h2>
        <ul className="mt-3 space-y-2">
          {OVERVIEW.users.items.map((user) => (
            <li key={user.who} className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3">
              <p className="text-sm font-semibold text-[var(--text-primary)]">{user.who}</p>
              <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{user.need}</p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="bc-what-it-does" className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
        <h2 id="bc-what-it-does" className="text-lg font-semibold text-[var(--text-primary)]">
          {OVERVIEW.whatItDoes.heading}
        </h2>
        <ol className="mt-3 space-y-2">
          {OVERVIEW.whatItDoes.steps.map((step, index) => (
            <li
              key={step.title}
              className="flex items-start gap-3 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3"
            >
              <span
                aria-hidden="true"
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-fill)] text-xs font-bold text-[var(--accent-ink)]"
              >
                {index + 1}
              </span>
              <span>
                <span className="block text-sm font-semibold text-[var(--text-primary)]">{step.title}</span>
                <span className="mt-1 block text-sm leading-relaxed text-[var(--text-secondary)]">{step.text}</span>
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="bc-why-architecture" className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
        <h2 id="bc-why-architecture" className="text-lg font-semibold text-[var(--text-primary)]">
          {OVERVIEW.whyThisArchitecture.heading}
        </h2>
        <ul className="mt-3 space-y-2">
          {OVERVIEW.whyThisArchitecture.reasons.map((reason) => (
            <li key={reason.title} className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3">
              <p className="text-sm font-semibold text-[var(--text-primary)]">{reason.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{reason.text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="bc-not-claimed"
        data-callout="not-claimed"
        className="rounded-[var(--radius-lg)] border-2 border-[var(--border-strong)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--warning)]">What is not claimed</p>
        <h2 id="bc-not-claimed" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {OVERVIEW.notClaimed.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{OVERVIEW.notClaimed.intro}</p>
        <ul className="mt-3 space-y-2">
          {OVERVIEW.notClaimed.items.map((item) => (
            <li key={item} className="flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3">
              <span aria-hidden="true" className="mt-0.5 text-[var(--warning)]">
                &#9888;
              </span>
              <span className="text-sm leading-relaxed text-[var(--text-secondary)]">{item}</span>
            </li>
          ))}
        </ul>
      </section>

      <CrossLinks current="overview" onNavigate={onNavigate} />
    </div>
  );
}
