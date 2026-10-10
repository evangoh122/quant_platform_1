import type { ReactNode } from 'react';
import {
  NAV_LINKS,
  SNAPSHOT,
  type RoadmapStatus,
  type RubricDeliveryStatus,
  type RubricImprovementStatus,
  type FunnelStage,
} from '../data/businessCase';

export type BusinessCasePageKey = 'overview' | 'data' | 'infrastructure' | 'features' | 'controls' | 'rubric';

export interface BusinessCaseScreenProps {
  onNavigate: (id: string) => void;
}

export const SCREEN_IDS: Record<BusinessCasePageKey, string> = {
  overview: 'business-case-overview',
  data: 'business-case-data',
  infrastructure: 'business-case-infrastructure',
  features: 'business-case-features',
  controls: 'business-case-controls',
  rubric: 'business-case-rubric',
};

export function screenIdForPage(page: BusinessCasePageKey): string {
  return SCREEN_IDS[page];
}

export const PAGE_LABELS: Record<BusinessCasePageKey, string> = {
  overview: NAV_LINKS.overview,
  data: NAV_LINKS.data,
  infrastructure: NAV_LINKS.infrastructure,
  features: NAV_LINKS.features,
  controls: NAV_LINKS.controls,
  rubric: NAV_LINKS.rubric,
};

export const PAGE_KEYS: BusinessCasePageKey[] = ['overview', 'data', 'infrastructure', 'features', 'controls', 'rubric'];

export const DATA_STATUS_LABELS: Record<'loaded' | 'partial' | 'planned', string> = {
  loaded: 'Loaded',
  partial: 'Partial',
  planned: 'Planned',
};

export const PLANNED_STATUS_LABELS: Record<'planned' | 'built-not-deployed' | 'blocked-on-owner', string> = {
  planned: 'Planned',
  'built-not-deployed': 'Built, not deployed',
  'blocked-on-owner': 'Blocked on owner',
};

export const ROADMAP_STATUS_LABELS: Record<RoadmapStatus, string> = {
  'not-started': 'Not started',
  'partly-built': 'Partly built',
};

export const RUBRIC_DELIVERY_STATUS_LABELS: Record<RubricDeliveryStatus, string> = {
  built: 'Built',
  'partly-built': 'Partly built',
  planned: 'Planned',
  'needs-live-proof': 'Needs live proof',
};

export const RUBRIC_IMPROVEMENT_STATUS_LABELS: Record<RubricImprovementStatus, string> = {
  planned: 'Planned',
  'not-started': 'Not started',
  'blocked-on-owner': 'Blocked on owner',
};

export const FUNNEL_STAGE_LABELS: Record<FunnelStage, string> = {
  bronze: 'Bronze',
  filter: 'Filter',
  silver: 'Silver',
  gold: 'Gold',
};

export const EVIDENCE_GAP_STATUS_LABELS: Record<'verified-present' | 'unverified' | 'absent', string> = {
  'verified-present': 'Verified present',
  unverified: 'Unverified',
  absent: 'Absent',
};

export function PageIntro({ eyebrow, title, thought }: { eyebrow: string; title: string; thought: string }) {
  return (
    <header className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-6">
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">{eyebrow}</p>
      <h1 className="mt-2 text-2xl font-bold text-[var(--text-primary)]">{title}</h1>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[var(--text-secondary)]">{thought}</p>
    </header>
  );
}

export function SnapshotStrip() {
  return (
    <section
      aria-label="Snapshot, not live"
      className="rounded-[var(--radius-md)] border border-warning-dim-30 bg-warning-dim-5 p-4"
    >
      <p className="flex items-center gap-2 text-sm font-semibold text-warning-text">
        <span aria-hidden="true">&#9888;</span> Snapshot, not live
      </p>
      <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">{SNAPSHOT.asOfLabel}</p>
      <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{SNAPSHOT.notLiveNote}</p>
    </section>
  );
}

export function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
      {children}
    </span>
  );
}

export function StatusBadge({ code, label }: { code: string; label: string }) {
  return (
    <span
      data-status={code}
      className="inline-flex items-center rounded-full border border-[var(--border-strong)] bg-[var(--surface-raised)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)]"
    >
      {label}
    </span>
  );
}

export function EvidenceLine({ text }: { text: string }) {
  return (
    <div className="mt-2">
      <FieldLabel>Evidence</FieldLabel>
      <p className="break-words text-xs text-[var(--text-secondary)]" data-mono>
        {text}
      </p>
    </div>
  );
}

export function ScrollRegion({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      className="overflow-x-auto rounded-[var(--radius-md)] border border-[var(--border)]"
    >
      {children}
    </div>
  );
}

export function CrossLinks({
  current,
  onNavigate,
}: {
  current: BusinessCasePageKey;
  onNavigate: (id: string) => void;
}) {
  return (
    <nav
      aria-label="Business case pages"
      className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)] p-4"
    >
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">Business case pages</p>
      <ul className="mt-3 flex flex-wrap gap-2">
        {PAGE_KEYS.map((page) => (
          <li key={page}>
            {page === current ? (
              <span
                data-crosslink-page={page}
                aria-current="page"
                className="inline-flex min-h-[44px] items-center rounded-[var(--radius-md)] border border-[var(--accent)] bg-[var(--accent-dim)] px-4 py-2 text-sm font-medium text-[var(--accent-bright)]"
              >
                {PAGE_LABELS[page]}
              </span>
            ) : (
              <button
                type="button"
                data-crosslink-page={page}
                onClick={() => onNavigate(screenIdForPage(page))}
                className="inline-flex min-h-[44px] items-center rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-4 py-2 text-sm font-medium text-[var(--text-primary)] transition hover:bg-[var(--surface-raised)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
              >
                {PAGE_LABELS[page]}
              </button>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
