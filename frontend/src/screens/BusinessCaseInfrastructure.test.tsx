import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { INFRASTRUCTURE, SNAPSHOT } from '../data/businessCase';
import { BusinessCaseInfrastructure } from './BusinessCaseInfrastructure';
import { expectStringsInDom, expectHeadingOrder } from '../test/contentStrings';

const EXPECTED_SCREEN_IDS: Record<string, string> = {
  overview: 'business-case-overview',
  data: 'business-case-data',
  infrastructure: 'business-case-infrastructure',
  features: 'business-case-features',
  controls: 'business-case-controls',
  rubric: 'business-case-rubric',
};

const FUTURE_STATUS_TEXT: Record<'planned' | 'built-not-deployed' | 'blocked-on-owner', string> = {
  planned: 'Planned',
  'built-not-deployed': 'Built, not deployed',
  'blocked-on-owner': 'Blocked on owner',
};

describe('BusinessCaseInfrastructure rendering', () => {
  it('renders every string field of SNAPSHOT and INFRASTRUCTURE exactly as written', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    expectStringsInDom(container, SNAPSHOT, 'SNAPSHOT');
    expectStringsInDom(container, INFRASTRUCTURE, 'INFRASTRUCTURE');
  });

  it('shows the labelled snapshot strip with asOfLabel on the infrastructure page', () => {
    render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    const strip = screen.getByRole('region', { name: 'Snapshot, not live' });
    expect(strip.textContent).toContain(SNAPSHOT.asOfLabel);
    expect(strip.textContent).toContain(SNAPSHOT.notLiveNote);
  });

  it('shows the governing thought before any evidence', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    const text = container.textContent ?? '';
    expect(text.indexOf(INFRASTRUCTURE.governingThought)).toBeLessThan(text.indexOf(INFRASTRUCTURE.flow[0].label));
  });

  it('renders the pipeline flow as ordered steps', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    const steps = Array.from(container.querySelectorAll('[data-flow-id]'));
    expect(steps).toHaveLength(INFRASTRUCTURE.flow.length);
    steps.forEach((el, index) => {
      expect(el.getAttribute('data-flow-id')).toBe(INFRASTRUCTURE.flow[index].id);
      expect(el.textContent).toContain(INFRASTRUCTURE.flow[index].label);
      expect(el.textContent).toContain(INFRASTRUCTURE.flow[index].role);
    });
  });

  it('renders every source with its fields', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    for (const source of INFRASTRUCTURE.sources) {
      const el = container.querySelector(`[data-source="${source.name}"]`)!;
      expect(el).not.toBeNull();
      expect(el.textContent).toContain(source.name);
      expect(el.textContent).toContain(source.whatItProvides);
      expect(el.textContent).toContain(source.howObtained);
      expect(el.textContent).toContain(source.lands);
    }
  });

  it('renders every layer with its items', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    for (const layer of INFRASTRUCTURE.layers) {
      const section = container.querySelector(`[data-layer-id="${layer.id}"]`)!;
      expect(section).not.toBeNull();
      expect(section.textContent).toContain(layer.heading);
      expect(section.textContent).toContain(layer.conclusion);
      const items = section.querySelectorAll('[data-layer-item]');
      expect(items).toHaveLength(layer.items.length);
      items.forEach((itemEl, index) => {
        expect(itemEl.textContent).toContain(layer.items[index].name);
        expect(itemEl.textContent).toContain(layer.items[index].what);
        if (layer.items[index].rowsLabel) {
          expect(itemEl.textContent).toContain(layer.items[index].rowsLabel);
        }
        if (layer.items[index].asOf) {
          expect(itemEl.textContent).toContain(layer.items[index].asOf);
        }
      });
    }
  });

  it('renders the funnel table with all steps', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    const rows = Array.from(container.querySelectorAll('[data-funnel-stage]'));
    expect(rows).toHaveLength(INFRASTRUCTURE.funnel.steps.length);
    rows.forEach((row, index) => {
      expect(row.getAttribute('data-funnel-stage')).toBe(INFRASTRUCTURE.funnel.steps[index].stage);
      expect(row.textContent).toContain(INFRASTRUCTURE.funnel.steps[index].count);
      expect(row.textContent).toContain(INFRASTRUCTURE.funnel.steps[index].label);
    });
  });

  it('renders the caveat beside the funnel', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    expect(container.textContent).toContain(INFRASTRUCTURE.funnel.caveat);
  });

  it('renders the why-not-everything-is-in-silver block', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    expect(container.textContent).toContain(INFRASTRUCTURE.whyNotEverythingIsInSilver.heading);
    expect(container.textContent).toContain(INFRASTRUCTURE.whyNotEverythingIsInSilver.text);
    for (const point of INFRASTRUCTURE.whyNotEverythingIsInSilver.points) {
      expect(container.textContent).toContain(point.text);
    }
  });

  it('renders future items with text status badges', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    for (const item of INFRASTRUCTURE.future.items) {
      const el = container.querySelector(`[data-future-id="${item.id}"]`)!;
      expect(el).not.toBeNull();
      const badge = el.querySelector('[data-status]')!;
      expect(badge.getAttribute('data-status')).toBe(item.status);
      expect(badge.textContent).toBe(FUTURE_STATUS_TEXT[item.status]);
      expect(el.textContent).toContain(item.existsToday);
      expect(el.textContent).toContain(item.stillToDo);
    }
  });
});

describe('BusinessCaseInfrastructure navigation and accessibility', () => {
  it('cross-links navigate to the other pages with the correct screen ids', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BusinessCaseInfrastructure onNavigate={onNavigate} />);

    const nav = screen.getByRole('navigation', { name: 'Business case pages' });
    expect(within(nav).getByText('Infrastructure').closest('[aria-current="page"]')).not.toBeNull();

    for (const page of ['overview', 'data', 'features', 'controls', 'rubric']) {
      const label = { overview: 'Overview', data: 'Data', features: 'Features', controls: 'Controls', rubric: 'Rubric plan' }[page]!;
      await user.click(within(nav).getByRole('button', { name: label }));
      expect(onNavigate).toHaveBeenLastCalledWith(EXPECTED_SCREEN_IDS[page]);
    }
  });

  it('keeps heading order and landmarks', () => {
    const { container } = render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    expectHeadingOrder(container);
    expect(container.querySelector('header')).not.toBeNull();
    expect(screen.getByRole('navigation', { name: 'Business case pages' })).toBeInTheDocument();
  });

  it('never calls fetch', () => {
    const fetchSpy = vi.fn(() => {
      throw new Error('business case pages must not call fetch');
    });
    vi.stubGlobal('fetch', fetchSpy);
    render(<BusinessCaseInfrastructure onNavigate={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});