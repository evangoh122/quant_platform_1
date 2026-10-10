import { RUBRIC_AI } from '../data/businessCase';
import {
  CrossLinks,
  EVIDENCE_GAP_STATUS_LABELS,
  EvidenceLine,
  FieldLabel,
  RUBRIC_DELIVERY_STATUS_LABELS,
  RUBRIC_IMPROVEMENT_STATUS_LABELS,
  PageIntro,
  ScrollRegion,
  SnapshotStrip,
  StatusBadge,
  type BusinessCaseScreenProps,
} from './businessCaseShared';

export function BusinessCaseRubric({ onNavigate }: BusinessCaseScreenProps) {
  return (
    <div className="space-y-8">
      <PageIntro eyebrow={RUBRIC_AI.eyebrow} title={RUBRIC_AI.title} thought={RUBRIC_AI.governingThought} />

      <SnapshotStrip />

      <section
        aria-labelledby="bc-rubric-basis"
        data-callout="basis"
        className="rounded-[var(--radius-lg)] border-2 border-[var(--border-strong)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Basis</p>
        <h2 id="bc-rubric-basis" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {RUBRIC_AI.basis.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{RUBRIC_AI.basis.text}</p>
        <div className="mt-3 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3">
          <FieldLabel>Delivery status legend</FieldLabel>
          <p className="text-sm leading-relaxed text-[var(--text-primary)]">{RUBRIC_AI.basis.deliveryStatusNote}</p>
        </div>
        <EvidenceLine text={RUBRIC_AI.basis.evidence} />
      </section>

      <section
        aria-labelledby="bc-rubric-plan-delivery"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Plan and delivery</p>
        <h2 id="bc-rubric-plan-delivery" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {RUBRIC_AI.planAndDelivery.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
          {RUBRIC_AI.planAndDelivery.intro}
        </p>

        <div className="mt-4 space-y-4">
          {RUBRIC_AI.planAndDelivery.rows.map((row) => (
            <article
              key={row.id}
              data-criterion-id={row.id}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{row.category}</h3>
                <StatusBadge code={row.deliveryStatus} label={RUBRIC_DELIVERY_STATUS_LABELS[row.deliveryStatus]} />
              </div>

              <div className="mt-3">
                <FieldLabel>Points available</FieldLabel>
                <p className="text-sm font-medium text-[var(--text-primary)]">{row.pointsPossible}</p>
              </div>

              <div className="mt-2">
                <FieldLabel>What the grader looks for</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{row.whatTheGraderLooksFor}</p>
              </div>

              <div className="mt-2">
                <FieldLabel>Our plan</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{row.ourPlan}</p>
              </div>

              <div className="mt-2">
                <FieldLabel>What we built</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{row.whatWeBuilt}</p>
              </div>

              <div className="mt-2">
                <FieldLabel>What is still open</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{row.stillOpen}</p>
              </div>

              <div className="mt-2">
                <FieldLabel>How to verify</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-primary)]">{row.howToVerify}</p>
              </div>

              <EvidenceLine text={row.evidence} />
            </article>
          ))}
        </div>
      </section>

      <section
        aria-labelledby="bc-rubric-decisions"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Design decisions</p>
        <h2 id="bc-rubric-decisions" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {RUBRIC_AI.designDecisions.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
          {RUBRIC_AI.designDecisions.intro}
        </p>
        <ul className="mt-4 space-y-3">
          {RUBRIC_AI.designDecisions.items.map((item) => (
            <li
              key={item.id}
              data-decision-id={item.id}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{item.rubricRule}</h3>
                <StatusBadge code={item.status} label={RUBRIC_DELIVERY_STATUS_LABELS[item.status]} />
              </div>
              <div className="mt-2">
                <FieldLabel>Decision</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{item.decision}</p>
              </div>
              <div className="mt-2">
                <FieldLabel>Why</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{item.why}</p>
              </div>
              <div className="mt-2">
                <FieldLabel>Tradeoff</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{item.tradeoff}</p>
              </div>
              <EvidenceLine text={item.evidence} />
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="bc-rubric-agent"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Agent</p>
        <h2 id="bc-rubric-agent" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {RUBRIC_AI.agent.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{RUBRIC_AI.agent.intro}</p>

        <ul className="mt-4 space-y-3">
          {RUBRIC_AI.agent.capabilities.map((cap) => (
            <li
              key={cap.title}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">{cap.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{cap.text}</p>
              <EvidenceLine text={cap.evidence} />
            </li>
          ))}
        </ul>

        <section aria-labelledby="bc-rubric-safety" className="mt-6">
          <h3 id="bc-rubric-safety" className="text-base font-semibold text-[var(--text-primary)]">
            {RUBRIC_AI.agent.safetyModel.heading}
          </h3>
          <ol className="mt-3 space-y-3">
            {RUBRIC_AI.agent.safetyModel.steps.map((step, index) => (
              <li
                key={step.title}
                className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
              >
                <div className="flex items-start gap-3">
                  <span
                    aria-hidden="true"
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--accent-fill)] text-xs font-bold text-[var(--accent-ink)]"
                  >
                    {index + 1}
                  </span>
                  <div>
                    <h4 className="text-sm font-semibold text-[var(--text-primary)]">{step.title}</h4>
                    <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{step.text}</p>
                    <div className="mt-2">
                      <FieldLabel>Enforced in</FieldLabel>
                      <p className="break-words text-xs text-[var(--text-muted)]" data-mono>{step.enforcedIn}</p>
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ol>
          <ul className="mt-3 space-y-2">
            {RUBRIC_AI.agent.safetyModel.caveats.map((caveat, index) => (
              <li
                key={index}
                className="flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-3"
              >
                <span aria-hidden="true" className="mt-0.5 text-[var(--warning)]">&#9888;</span>
                <span className="text-sm leading-relaxed text-[var(--text-secondary)]">{caveat}</span>
              </li>
            ))}
          </ul>
        </section>
      </section>

      <section
        aria-labelledby="bc-rubric-strengths"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Strengths</p>
        <h2 id="bc-rubric-strengths" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {RUBRIC_AI.strengths.heading}
        </h2>
        <ul className="mt-4 space-y-3">
          {RUBRIC_AI.strengths.items.map((item) => (
            <li
              key={item.title}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">{item.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{item.text}</p>
              <EvidenceLine text={item.evidence} />
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="bc-rubric-evidence-gaps"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Evidence gaps</p>
        <h2 id="bc-rubric-evidence-gaps" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {RUBRIC_AI.evidenceGaps.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
          {RUBRIC_AI.evidenceGaps.intro}
        </p>
        <ul className="mt-4 space-y-3">
          {RUBRIC_AI.evidenceGaps.items.map((item) => (
            <li
              key={item.item}
              data-evidence-gap={item.item}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{item.item}</h3>
                <StatusBadge code={item.status} label={EVIDENCE_GAP_STATUS_LABELS[item.status]} />
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{item.note}</p>
              <EvidenceLine text={item.evidence} />
            </li>
          ))}
        </ul>
      </section>

      <section
        aria-labelledby="bc-rubric-demo"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Demo script</p>
        <h2 id="bc-rubric-demo" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {RUBRIC_AI.demoScript.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
          {RUBRIC_AI.demoScript.intro}
        </p>
        <ol className="mt-4 space-y-3">
          {RUBRIC_AI.demoScript.steps.map((step) => (
            <li
              key={step.order}
              data-demo-order={step.order}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                Step {step.order}: {step.category}
              </h3>
              <div className="mt-2">
                <FieldLabel>Show</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{step.show}</p>
              </div>
              <div className="mt-2">
                <FieldLabel>Proves</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{step.proves}</p>
              </div>
              <div className="mt-2">
                <FieldLabel>How</FieldLabel>
                <p className="text-sm leading-relaxed text-[var(--text-primary)]">{step.how}</p>
              </div>
              <div className="mt-2">
                <FieldLabel>Criteria</FieldLabel>
                <p className="text-xs text-[var(--text-muted)]">{step.rubricCriterionIds.join(', ')}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section
        aria-labelledby="bc-rubric-improvements"
        className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-5"
      >
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Planned improvements</p>
        <h2 id="bc-rubric-improvements" className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
          {RUBRIC_AI.plannedImprovements.heading}
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">
          {RUBRIC_AI.plannedImprovements.intro}
        </p>
        <ul className="mt-4 space-y-3">
          {RUBRIC_AI.plannedImprovements.items.map((item) => (
            <li
              key={item.id}
              data-improvement-id={item.id}
              className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{item.action}</h3>
                <StatusBadge code={item.status} label={RUBRIC_IMPROVEMENT_STATUS_LABELS[item.status]} />
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{item.why}</p>
            </li>
          ))}
        </ul>
      </section>

      <CrossLinks current="rubric" onNavigate={onNavigate} />
    </div>
  );
}