import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { FEATURES, NEXT_APPROACH, SNAPSHOT } from '../data/businessCase';
import { BusinessCaseFeatures } from './BusinessCaseFeatures';
import { expectStringsInDom, expectHeadingOrder } from '../test/contentStrings';

const EXPECTED_SCREEN_IDS: Record<string, string> = {
  overview: 'business-case-overview',
  data: 'business-case-data',
  features: 'business-case-features',
  controls: 'business-case-controls',
};

const PLANNED_STATUS_TEXT: Record<'planned' | 'built-not-deployed' | 'blocked-on-owner', string> = {
  planned: 'Planned',
  'built-not-deployed': 'Built, not deployed',
  'blocked-on-owner': 'Blocked on owner',
};

const ROADMAP_STATUS_TEXT: Record<'not-started' | 'partly-built', string> = {
  'not-started': 'Not started',
  'partly-built': 'Partly built',
};

describe('BusinessCaseFeatures rendering', () => {
  it('renders every string field of SNAPSHOT, FEATURES and NEXT_APPROACH exactly as written', () => {
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    expectStringsInDom(container, SNAPSHOT, 'SNAPSHOT');
    expectStringsInDom(container, FEATURES, 'FEATURES');
    expectStringsInDom(container, NEXT_APPROACH, 'NEXT_APPROACH');
  });

  it('shows the labelled snapshot strip with asOfLabel on the features page', () => {
    render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    const strip = screen.getByRole('region', { name: 'Snapshot, not live' });
    expect(strip.textContent).toContain(SNAPSHOT.asOfLabel);
  });

  it('shows the governing thought before any feature evidence', () => {
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    const text = container.textContent ?? '';
    expect(text.indexOf(FEATURES.governingThought)).toBeLessThan(text.indexOf(FEATURES.available[0].heading));
  });

  it('renders available and planned items with their headings, text and status labels', () => {
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    for (const item of FEATURES.available) {
      const el = container.querySelector(`[data-item-id="${item.id}"]`)!;
      expect(el).not.toBeNull();
      expect(el.textContent).toContain(item.heading);
      expect(el.textContent).toContain(item.text);
      expect(el.textContent).toContain(item.evidence);
    }
    for (const item of FEATURES.planned) {
      const el = container.querySelector(`[data-item-id="${item.id}"]`)!;
      expect(el).not.toBeNull();
      const badge = el.querySelector('[data-status]')!;
      expect(badge.getAttribute('data-status')).toBe(item.status);
      expect(badge.textContent).toBe(PLANNED_STATUS_TEXT[item.status]);
      expect(el.textContent).toContain(item.text);
      expect(el.textContent).toContain(item.why);
    }
  });
});

describe('BusinessCaseFeatures roadmap', () => {
  it('shows the unmissable status banner with statusLabel and statusNote before any roadmap step', () => {
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);

    const banner = container.querySelector('[data-roadmap-banner]')!;
    expect(banner).not.toBeNull();
    expect(banner.textContent).toContain(NEXT_APPROACH.statusLabel);
    expect(banner.textContent).toContain(NEXT_APPROACH.statusNote);

    const firstStep = container.querySelector('[data-step-id]')!;
    expect(firstStep).not.toBeNull();
    expect(banner.compareDocumentPosition(firstStep) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders the insteadOf contrast block with from and to', () => {
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    const from = container.querySelector('[data-insteadof="from"]')!;
    const to = container.querySelector('[data-insteadof="to"]')!;
    expect(from.textContent).toContain(NEXT_APPROACH.insteadOf.from);
    expect(to.textContent).toContain(NEXT_APPROACH.insteadOf.to);
  });

  it('renders roadmap steps in order with text status badges and dependency lines', () => {
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    const steps = Array.from(container.querySelectorAll('[data-step-id]'));
    expect(steps).toHaveLength(NEXT_APPROACH.whatWeIntendToDo.steps.length);

    const orderById = new Map(NEXT_APPROACH.whatWeIntendToDo.steps.map((s) => [s.id, s.order]));
    steps.forEach((el, index) => {
      const step = NEXT_APPROACH.whatWeIntendToDo.steps[index];
      expect(el.getAttribute('data-step-id')).toBe(step.id);
      expect(el.getAttribute('data-step-order')).toBe(String(step.order));
      expect(el.textContent).toContain(step.title);
      expect(el.textContent).toContain(step.text);
      expect(el.textContent).toContain(step.whyItMatters);
      expect(el.textContent).toContain(step.proposedArtifact);
      expect(el.textContent).toContain(step.acceptance);
      expect(el.textContent).toContain(step.existsToday);
      expect(el.textContent).toContain(step.stillToDo);
      expect(el.textContent).toContain(step.evidence);

      const badge = el.querySelector('[data-status]')!;
      expect(badge.getAttribute('data-status')).toBe(step.status);
      expect(badge.textContent).toBe(ROADMAP_STATUS_TEXT[step.status]);
      expect(badge.textContent && badge.textContent.trim().length).toBeGreaterThan(0);

      for (const dependencyId of step.dependsOn) {
        const dependency = el.querySelector(`[data-depends-on="${dependencyId}"]`)!;
        expect(dependency).not.toBeNull();
        expect(dependency.textContent).toContain(`Depends on step ${orderById.get(dependencyId)}`);
      }
    });

    const orders = steps.map((el) => Number(el.getAttribute('data-step-order')));
    expect(orders).toEqual([...orders].sort((a, b) => a - b));
  });

  it('labels the proposed artifact field on every step', () => {
    render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    expect(screen.getAllByText('Proposed artifact')).toHaveLength(NEXT_APPROACH.whatWeIntendToDo.steps.length);
  });

  it('renders the studies as a compact table inside an accessible labelled container', () => {
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    const region = screen.getByRole('region', { name: 'Roadmap studies' });
    expect(region.getAttribute('tabindex')).toBe('0');
    const table = region.querySelector('table')!;
    expect(table).not.toBeNull();
    const rows = table.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(NEXT_APPROACH.studies.items.length);
    for (const study of NEXT_APPROACH.studies.items) {
      expect(container.textContent).toContain(study.name);
    }
  });

  it('renders how we will judge it and the honest outlook', () => {
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    expect(container.textContent).toContain(NEXT_APPROACH.howWeWillJudgeIt.heading);
    for (const item of NEXT_APPROACH.howWeWillJudgeIt.items) {
      expect(container.textContent).toContain(item);
    }
    expect(container.textContent).toContain(NEXT_APPROACH.honestOutlook.heading);
    expect(container.textContent).toContain(NEXT_APPROACH.honestOutlook.text);
  });

  it('honesty guard: every roadmap step status is allowed and the page never claims coming soon or will deliver', () => {
    for (const step of NEXT_APPROACH.whatWeIntendToDo.steps) {
      expect(['not-started', 'partly-built']).toContain(step.status);
    }
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    const text = (container.textContent ?? '').toLowerCase();
    expect(text).not.toContain('coming soon');
    expect(text).not.toContain('will deliver');
  });
});

describe('BusinessCaseFeatures navigation and accessibility', () => {
  it('cross-links navigate to the other pages with the correct screen ids', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BusinessCaseFeatures onNavigate={onNavigate} />);

    const nav = screen.getByRole('navigation', { name: 'Business case pages' });
    expect(within(nav).getByText('Features').closest('[aria-current="page"]')).not.toBeNull();

    for (const page of ['overview', 'data', 'controls']) {
      const label = { overview: 'Overview', data: 'Data', controls: 'Controls' }[page]!;
      await user.click(within(nav).getByRole('button', { name: label }));
      expect(onNavigate).toHaveBeenLastCalledWith(EXPECTED_SCREEN_IDS[page]);
    }
  });

  it('keeps heading order and landmarks', () => {
    const { container } = render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    expectHeadingOrder(container);
    expect(container.querySelector('header')).not.toBeNull();
    expect(screen.getByRole('navigation', { name: 'Business case pages' })).toBeInTheDocument();
  });

  it('never calls fetch', () => {
    const fetchSpy = vi.fn(() => {
      throw new Error('business case pages must not call fetch');
    });
    vi.stubGlobal('fetch', fetchSpy);
    render(<BusinessCaseFeatures onNavigate={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
