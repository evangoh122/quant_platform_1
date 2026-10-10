import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { DATA, SNAPSHOT } from '../data/businessCase';
import { BusinessCaseData } from './BusinessCaseData';
import { expectStringsInDom, expectHeadingOrder } from '../test/contentStrings';

const EXPECTED_SCREEN_IDS: Record<string, string> = {
  overview: 'business-case-overview',
  data: 'business-case-data',
  features: 'business-case-features',
  controls: 'business-case-controls',
};

const STATUS_TEXT: Record<'loaded' | 'partial' | 'planned', string> = {
  loaded: 'Loaded',
  partial: 'Partial',
  planned: 'Planned',
};

describe('BusinessCaseData rendering', () => {
  it('renders every string field of SNAPSHOT and DATA exactly as written', () => {
    const { container } = render(<BusinessCaseData onNavigate={vi.fn()} />);
    expectStringsInDom(container, SNAPSHOT, 'SNAPSHOT');
    expectStringsInDom(container, DATA, 'DATA');
  });

  it('shows the labelled snapshot strip with asOfLabel on the data page', () => {
    render(<BusinessCaseData onNavigate={vi.fn()} />);
    const strip = screen.getByRole('region', { name: 'Snapshot, not live' });
    expect(strip.textContent).toContain(SNAPSHOT.asOfLabel);
    expect(strip.textContent).toContain(SNAPSHOT.notLiveNote);
  });

  it('renders a StatTile for every DATA tile', () => {
    render(<BusinessCaseData onNavigate={vi.fn()} />);
    for (const tile of DATA.tiles) {
      expect(screen.getByText(tile.label)).toBeInTheDocument();
      expect(screen.getByText(tile.value)).toBeInTheDocument();
      if (tile.note) {
        expect(screen.getByText(tile.note)).toBeInTheDocument();
      }
    }
    const figures = document.querySelector('[data-snapshot-figures]')!;
    expect(figures.querySelectorAll('.stat-card')).toHaveLength(DATA.tiles.length);
  });

  it('shows every data row status as a text badge with an accessible name', () => {
    const { container } = render(<BusinessCaseData onNavigate={vi.fn()} />);
    for (const group of DATA.groups) {
      for (const row of group.rows) {
        const rowEl = container.querySelector(`[data-row="${row.name.replace(/"/g, '\\"')}"]`)!;
        expect(rowEl).not.toBeNull();
        const badge = rowEl.querySelector('[data-status]')!;
        expect(badge.getAttribute('data-status')).toBe(row.status);
        expect(badge.textContent).toBe(STATUS_TEXT[row.status]);
        expect(badge.textContent && badge.textContent.trim().length).toBeGreaterThan(0);
      }
    }
  });

  it('shows the governing thought before any data evidence', () => {
    const { container } = render(<BusinessCaseData onNavigate={vi.fn()} />);
    const text = container.textContent ?? '';
    expect(text.indexOf(DATA.governingThought)).toBeLessThan(text.indexOf(DATA.tiles[0].label));
    expect(text.indexOf(DATA.governingThought)).toBeLessThan(text.indexOf(DATA.groups[0].heading));
  });

  it('renders each group as a section with its takeaway heading, conclusion and rows in order', () => {
    const { container } = render(<BusinessCaseData onNavigate={vi.fn()} />);
    DATA.groups.forEach((group) => {
      const section = container.querySelector(`[data-group-id="${group.id}"]`)!;
      expect(section).not.toBeNull();
      expect(section.textContent).toContain(group.heading);
      expect(section.textContent).toContain(group.conclusion);
      const rows = section.querySelectorAll('[data-row]');
      expect(rows).toHaveLength(group.rows.length);
      rows.forEach((rowEl, index) => {
        expect(rowEl.textContent).toContain(group.rows[index].name);
        expect(rowEl.textContent).toContain(group.rows[index].what);
      });
    });
  });
});

describe('BusinessCaseData navigation and accessibility', () => {
  it('cross-links navigate to the other pages with the correct screen ids', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BusinessCaseData onNavigate={onNavigate} />);

    const nav = screen.getByRole('navigation', { name: 'Business case pages' });
    expect(within(nav).getByText('Data').closest('[aria-current="page"]')).not.toBeNull();

    for (const page of ['overview', 'features', 'controls']) {
      const label = { overview: 'Overview', features: 'Features', controls: 'Controls' }[page]!;
      await user.click(within(nav).getByRole('button', { name: label }));
      expect(onNavigate).toHaveBeenLastCalledWith(EXPECTED_SCREEN_IDS[page]);
    }
  });

  it('keeps heading order and landmarks', () => {
    const { container } = render(<BusinessCaseData onNavigate={vi.fn()} />);
    expectHeadingOrder(container);
    expect(container.querySelector('header')).not.toBeNull();
    expect(screen.getByRole('navigation', { name: 'Business case pages' })).toBeInTheDocument();
  });

  it('never calls fetch', () => {
    const fetchSpy = vi.fn(() => {
      throw new Error('business case pages must not call fetch');
    });
    vi.stubGlobal('fetch', fetchSpy);
    render(<BusinessCaseData onNavigate={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
