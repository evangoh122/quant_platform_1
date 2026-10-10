import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { RUBRIC_AI, SNAPSHOT } from '../data/businessCase';
import { BusinessCaseRubric } from './BusinessCaseRubric';
import { expectStringsInDom, expectHeadingOrder } from '../test/contentStrings';

const EXPECTED_SCREEN_IDS: Record<string, string> = {
  overview: 'business-case-overview',
  data: 'business-case-data',
  infrastructure: 'business-case-infrastructure',
  features: 'business-case-features',
  controls: 'business-case-controls',
  rubric: 'business-case-rubric',
};

const DELIVERY_STATUS_TEXT: Record<string, string> = {
  built: 'Built',
  'partly-built': 'Partly built',
  planned: 'Planned',
  'needs-live-proof': 'Needs live proof',
};

const IMPROVEMENT_STATUS_TEXT: Record<string, string> = {
  planned: 'Planned',
  'not-started': 'Not started',
  'blocked-on-owner': 'Blocked on owner',
};

const EVIDENCE_GAP_STATUS_TEXT: Record<string, string> = {
  'verified-present': 'Verified present',
  unverified: 'Unverified',
  absent: 'Absent',
};

describe('BusinessCaseRubric rendering', () => {
  it('renders every string field of SNAPSHOT and RUBRIC_AI exactly as written', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    expectStringsInDom(container, SNAPSHOT, 'SNAPSHOT');
    expectStringsInDom(container, RUBRIC_AI, 'RUBRIC_AI');
  });

  it('shows the labelled snapshot strip with asOfLabel on the rubric page', () => {
    render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    const strip = screen.getByRole('region', { name: 'Snapshot, not live' });
    expect(strip.textContent).toContain(SNAPSHOT.asOfLabel);
    expect(strip.textContent).toContain(SNAPSHOT.notLiveNote);
  });

  it('shows the governing thought before any evidence', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    const text = container.textContent ?? '';
    expect(text.indexOf(RUBRIC_AI.governingThought)).toBeLessThan(text.indexOf(RUBRIC_AI.basis.heading));
  });

  it('renders the basis statement prominently at the top', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    const basis = container.querySelector('[data-callout="basis"]')!;
    expect(basis).not.toBeNull();
    expect(basis.className).toContain('border-2');
    expect(basis.textContent).toContain(RUBRIC_AI.basis.heading);
    expect(basis.textContent).toContain(RUBRIC_AI.basis.text);
    expect(basis.textContent).toContain(RUBRIC_AI.basis.deliveryStatusNote);
  });

  it('renders all 12 plan-and-delivery rows with their fields', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    for (const row of RUBRIC_AI.planAndDelivery.rows) {
      const el = container.querySelector(`[data-criterion-id="${row.id}"]`)!;
      expect(el).not.toBeNull();
      expect(el.textContent).toContain(row.category);
      expect(el.textContent).toContain(String(row.pointsPossible));
      expect(el.textContent).toContain(row.whatTheGraderLooksFor);
      expect(el.textContent).toContain(row.ourPlan);
      expect(el.textContent).toContain(row.whatWeBuilt);
      expect(el.textContent).toContain(row.stillOpen);
      expect(el.textContent).toContain(row.howToVerify);
      const badge = el.querySelector('[data-status]')!;
      expect(badge.getAttribute('data-status')).toBe(row.deliveryStatus);
      expect(badge.textContent).toBe(DELIVERY_STATUS_TEXT[row.deliveryStatus]);
    }
  });

  it('renders the Points available label on every plan row', () => {
    render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    expect(screen.getAllByText('Points available')).toHaveLength(RUBRIC_AI.planAndDelivery.rows.length);
  });

  it('renders the design-decision log', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    for (const item of RUBRIC_AI.designDecisions.items) {
      const el = container.querySelector(`[data-decision-id="${item.id}"]`)!;
      expect(el).not.toBeNull();
      expect(el.textContent).toContain(item.rubricRule);
      expect(el.textContent).toContain(item.decision);
      expect(el.textContent).toContain(item.why);
      expect(el.textContent).toContain(item.tradeoff);
    }
  });

  it('renders agent capabilities and safety model', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    for (const cap of RUBRIC_AI.agent.capabilities) {
      expect(container.textContent).toContain(cap.title);
      expect(container.textContent).toContain(cap.text);
    }
    for (const step of RUBRIC_AI.agent.safetyModel.steps) {
      expect(container.textContent).toContain(step.title);
      expect(container.textContent).toContain(step.text);
    }
    for (const caveat of RUBRIC_AI.agent.safetyModel.caveats) {
      expect(container.textContent).toContain(caveat);
    }
  });

  it('renders strengths', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    for (const item of RUBRIC_AI.strengths.items) {
      expect(container.textContent).toContain(item.title);
      expect(container.textContent).toContain(item.text);
    }
  });

  it('renders evidence gaps with status words', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    for (const item of RUBRIC_AI.evidenceGaps.items) {
      const el = container.querySelector(`[data-evidence-gap="${item.item}"]`)!;
      expect(el).not.toBeNull();
      const badge = el.querySelector('[data-status]')!;
      expect(badge.getAttribute('data-status')).toBe(item.status);
      expect(badge.textContent).toBe(EVIDENCE_GAP_STATUS_TEXT[item.status]);
      expect(el.textContent).toContain(item.note);
    }
  });

  it('renders demo script as an ordered list', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    for (const step of RUBRIC_AI.demoScript.steps) {
      const el = container.querySelector(`[data-demo-order="${step.order}"]`)!;
      expect(el).not.toBeNull();
      expect(el.textContent).toContain(step.category);
      expect(el.textContent).toContain(step.show);
      expect(el.textContent).toContain(step.proves);
      expect(el.textContent).toContain(step.how);
      for (const id of step.rubricCriterionIds) {
        expect(el.textContent).toContain(id);
      }
    }
  });

  it('renders planned improvements with status words', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    for (const item of RUBRIC_AI.plannedImprovements.items) {
      const el = container.querySelector(`[data-improvement-id="${item.id}"]`)!;
      expect(el).not.toBeNull();
      const badge = el.querySelector('[data-status]')!;
      expect(badge.getAttribute('data-status')).toBe(item.status);
      expect(badge.textContent).toBe(IMPROVEMENT_STATUS_TEXT[item.status]);
      expect(el.textContent).toContain(item.action);
      expect(el.textContent).toContain(item.why);
    }
  });
});

describe('BusinessCaseRubric no-scores guard', () => {
  it('renders no score numerators, totals or score-like patterns', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    const text = container.textContent ?? '';
    expect(text).not.toMatch(/\d+\s*(\/|of|out of)\s*(15|10|6|8|5|100)\b/);
    expect(text.toLowerCase()).not.toContain('total');
    expect(text.toLowerCase()).not.toContain('scorecard');
    expect(text.toLowerCase()).not.toContain('self-assess');
  });

  it('the only numbers in the Points available column are the 12 weights', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    const pointsLabels = screen.getAllByText('Points available');
    const weights = RUBRIC_AI.planAndDelivery.rows.map((r) => r.pointsPossible);
    expect(pointsLabels).toHaveLength(12);
    for (const label of pointsLabels) {
      const parent = label.closest('[data-criterion-id]')!;
      const weightEl = parent.querySelector('.text-sm.font-medium')!;
      expect(weights).toContain(Number(weightEl.textContent));
    }
  });
});

describe('BusinessCaseRubric navigation and accessibility', () => {
  it('cross-links navigate to the other pages with the correct screen ids', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BusinessCaseRubric onNavigate={onNavigate} />);

    const nav = screen.getByRole('navigation', { name: 'Business case pages' });
    expect(within(nav).getByText('Rubric plan').closest('[aria-current="page"]')).not.toBeNull();

    for (const page of ['overview', 'data', 'infrastructure', 'features', 'controls']) {
      const label = { overview: 'Overview', data: 'Data', infrastructure: 'Infrastructure', features: 'Features', controls: 'Controls' }[page]!;
      await user.click(within(nav).getByRole('button', { name: label }));
      expect(onNavigate).toHaveBeenLastCalledWith(EXPECTED_SCREEN_IDS[page]);
    }
  });

  it('keeps heading order and landmarks', () => {
    const { container } = render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    expectHeadingOrder(container);
    expect(container.querySelector('header')).not.toBeNull();
    expect(screen.getByRole('navigation', { name: 'Business case pages' })).toBeInTheDocument();
  });

  it('never calls fetch', () => {
    const fetchSpy = vi.fn(() => {
      throw new Error('business case pages must not call fetch');
    });
    vi.stubGlobal('fetch', fetchSpy);
    render(<BusinessCaseRubric onNavigate={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});