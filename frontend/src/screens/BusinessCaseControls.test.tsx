import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { CONTROLS, SNAPSHOT } from '../data/businessCase';
import { BusinessCaseControls } from './BusinessCaseControls';
import { expectStringsInDom, expectHeadingOrder } from '../test/contentStrings';

const EXPECTED_SCREEN_IDS: Record<string, string> = {
  overview: 'business-case-overview',
  data: 'business-case-data',
  features: 'business-case-features',
  controls: 'business-case-controls',
};

describe('BusinessCaseControls rendering', () => {
  it('renders every string field of SNAPSHOT and CONTROLS exactly as written', () => {
    const { container } = render(<BusinessCaseControls onNavigate={vi.fn()} />);
    expectStringsInDom(container, SNAPSHOT, 'SNAPSHOT');
    expectStringsInDom(container, CONTROLS, 'CONTROLS');
  });

  it('shows the labelled snapshot strip with asOfLabel on the controls page', () => {
    render(<BusinessCaseControls onNavigate={vi.fn()} />);
    const strip = screen.getByRole('region', { name: 'Snapshot, not live' });
    expect(strip.textContent).toContain(SNAPSHOT.asOfLabel);
    expect(strip.textContent).toContain(SNAPSHOT.notLiveNote);
  });

  it('shows the governing thought before any control evidence', () => {
    const { container } = render(<BusinessCaseControls onNavigate={vi.fn()} />);
    const text = container.textContent ?? '';
    expect(text.indexOf(CONTROLS.governingThought)).toBeLessThan(text.indexOf(CONTROLS.groups[0].heading));
    expect(text.indexOf(CONTROLS.governingThought)).toBeLessThan(text.indexOf(CONTROLS.groups[0].items[0].control));
  });

  it('renders every control group with takeaway heading, conclusion and items', () => {
    const { container } = render(<BusinessCaseControls onNavigate={vi.fn()} />);
    for (const group of CONTROLS.groups) {
      const section = container.querySelector(`[data-group-id="${group.id}"]`)!;
      expect(section).not.toBeNull();
      expect(section.textContent).toContain(group.heading);
      expect(section.textContent).toContain(group.conclusion);
      const items = section.querySelectorAll('[data-control]');
      expect(items).toHaveLength(group.items.length);
      items.forEach((itemEl, index) => {
        expect(itemEl.textContent).toContain(group.items[index].control);
        expect(itemEl.textContent).toContain(group.items[index].how);
        expect(itemEl.textContent).toContain(group.items[index].enforcedIn);
      });
    }
  });

  it('renders known limitations with the same visual weight as the strengths', () => {
    const { container } = render(<BusinessCaseControls onNavigate={vi.fn()} />);
    expect(screen.getByText('Known limitations')).toBeInTheDocument();

    const limitations = container.querySelector('[data-group-id="known-limitations"]')!;
    expect(limitations).not.toBeNull();
    expect(limitations.className).toContain('border-2');
    expect(limitations.textContent).toContain(CONTROLS.limitations.heading);
    expect(limitations.textContent).toContain(CONTROLS.limitations.intro);

    const items = limitations.querySelectorAll('[data-limitation]');
    expect(items).toHaveLength(CONTROLS.limitations.items.length);
    items.forEach((itemEl, index) => {
      expect(itemEl.textContent).toContain(CONTROLS.limitations.items[index].limit);
      expect(itemEl.textContent).toContain(CONTROLS.limitations.items[index].impact);
    });

    const strengthSections = Array.from(container.querySelectorAll('[data-group-id]')).filter(
      (el) => el.getAttribute('data-group-id') !== 'known-limitations',
    );
    expect(strengthSections.length).toBeGreaterThan(0);
    for (const strength of strengthSections) {
      expect(limitations.classList.length).toBeGreaterThanOrEqual(strength.classList.length);
    }
  });
});

describe('BusinessCaseControls navigation and accessibility', () => {
  it('cross-links navigate to the other pages with the correct screen ids', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BusinessCaseControls onNavigate={onNavigate} />);

    const nav = screen.getByRole('navigation', { name: 'Business case pages' });
    expect(within(nav).getByText('Controls').closest('[aria-current="page"]')).not.toBeNull();

    for (const page of ['overview', 'data', 'features']) {
      const label = { overview: 'Overview', data: 'Data', features: 'Features' }[page]!;
      await user.click(within(nav).getByRole('button', { name: label }));
      expect(onNavigate).toHaveBeenLastCalledWith(EXPECTED_SCREEN_IDS[page]);
    }
  });

  it('keeps heading order and landmarks', () => {
    const { container } = render(<BusinessCaseControls onNavigate={vi.fn()} />);
    expectHeadingOrder(container);
    expect(container.querySelector('header')).not.toBeNull();
    expect(screen.getByRole('navigation', { name: 'Business case pages' })).toBeInTheDocument();
  });

  it('never calls fetch', () => {
    const fetchSpy = vi.fn(() => {
      throw new Error('business case pages must not call fetch');
    });
    vi.stubGlobal('fetch', fetchSpy);
    render(<BusinessCaseControls onNavigate={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
