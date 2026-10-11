import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { EXECUTIVE_SUMMARY, KEY_LINE, OVERVIEW, SNAPSHOT } from '../data/businessCase';
import { BusinessCaseOverview } from './BusinessCaseOverview';
import { expectStringsInDom, expectHeadingOrder } from '../test/contentStrings';

const EXPECTED_SCREEN_IDS: Record<string, string> = {
  overview: 'business-case-overview',
  data: 'business-case-data',
  infrastructure: 'business-case-infrastructure',
  features: 'business-case-features',
  controls: 'business-case-controls',
  rubric: 'business-case-rubric',
};

describe('BusinessCaseOverview rendering', () => {
  it('renders every string field of SNAPSHOT, EXECUTIVE_SUMMARY, KEY_LINE and OVERVIEW exactly as written', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    expectStringsInDom(container, SNAPSHOT, 'SNAPSHOT');
    expectStringsInDom(container, EXECUTIVE_SUMMARY, 'EXECUTIVE_SUMMARY');
    expectStringsInDom(container, KEY_LINE, 'KEY_LINE');
    expectStringsInDom(container, OVERVIEW, 'OVERVIEW');
  });

  it('shows the labelled snapshot strip with asOfLabel and notLiveNote', () => {
    render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    const strip = screen.getByRole('region', { name: 'Snapshot, not live' });
    expect(strip).toBeInTheDocument();
    expect(strip.textContent).toContain(SNAPSHOT.asOfLabel);
    expect(strip.textContent).toContain(SNAPSHOT.notLiveNote);
  });

  it('shows Situation, Complication, Question and Answer in that order with the Answer emphasised', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);

    const parts = Array.from(container.querySelectorAll('[data-scqa-part]'));
    expect(parts.map((el) => el.getAttribute('data-scqa-part'))).toEqual([
      'situation',
      'complication',
      'question',
      'answer',
    ]);

    for (const part of parts) {
      expect(part.textContent).toContain(part.getAttribute('aria-label') ?? '');
    }
    expect(parts[3].getAttribute('data-emphasis')).toBe('strong');
    expect(parts[0].getAttribute('data-emphasis')).toBe('standard');
    expect(parts[1].getAttribute('data-emphasis')).toBe('standard');
    expect(parts[2].getAttribute('data-emphasis')).toBe('standard');

    expect(screen.getByRole('heading', { name: 'Answer' })).toBeInTheDocument();
  });

  it('renders three key-line cards that navigate to their evidence pages', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BusinessCaseOverview onNavigate={onNavigate} />);

    const cards = Array.from(document.querySelectorAll('[data-argument-id]'));
    expect(cards).toHaveLength(3);
    expect(cards.map((el) => el.getAttribute('data-argument-id'))).toEqual(['data', 'features', 'controls']);
    expect(cards.map((el) => el.getAttribute('data-argument-page'))).toEqual(['data', 'features', 'controls']);

    for (const card of cards) {
      const page = card.getAttribute('data-argument-page') ?? '';
      await user.click(card as HTMLElement);
      expect(onNavigate).toHaveBeenLastCalledWith(EXPECTED_SCREEN_IDS[page]);
    }

    const argumentCard = document.querySelector('[data-argument-id="data"]')!;
    expect(argumentCard.textContent).toContain(KEY_LINE.arguments[0].claim);
    expect(argumentCard.textContent).toContain(KEY_LINE.arguments[0].proof);
  });

  it('shows the governing thought in the page header before any evidence', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    const text = container.textContent ?? '';
    expect(text.indexOf(OVERVIEW.governingThought)).toBeGreaterThanOrEqual(0);
    expect(text.indexOf(OVERVIEW.governingThought)).toBeLessThan(text.indexOf(OVERVIEW.users.items[0].who));
  });

  it('renders an assessment link that navigates to the rubric page', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BusinessCaseOverview onNavigate={onNavigate} />);

    const assessmentLink = document.querySelector('[data-assessment-link="rubric"]')!;
    expect(assessmentLink).not.toBeNull();
    expect(assessmentLink.textContent).toContain(KEY_LINE.assessment.label);
    expect(assessmentLink.textContent).toContain(KEY_LINE.assessment.text);
    await user.click(assessmentLink as HTMLElement);
    expect(onNavigate).toHaveBeenLastCalledWith('business-case-rubric');
  });

  it('renders what it does as numbered steps in data order', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    const list = container.querySelectorAll('ol');
    expect(list.length).toBeGreaterThanOrEqual(1);
    const steps = list[0].querySelectorAll(':scope > li');
    expect(steps).toHaveLength(OVERVIEW.whatItDoes.steps.length);
    steps.forEach((step, index) => {
      expect(step.textContent).toContain(OVERVIEW.whatItDoes.steps[index].title);
      expect(step.textContent).toContain(OVERVIEW.whatItDoes.steps[index].text);
    });
  });

  it('renders what is not claimed as a prominent bordered callout labelled by text', () => {
    render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    expect(screen.getByText('What is not claimed')).toBeInTheDocument();
    const callout = document.querySelector('[data-callout="not-claimed"]')!;
    expect(callout.className).toContain('border-2');
    expect(callout.textContent).toContain(OVERVIEW.notClaimed.heading);
    expect(callout.textContent).toContain(OVERVIEW.notClaimed.intro);
  });
});

describe('BusinessCaseOverview navigation and accessibility', () => {
  it('cross-links navigate to the other pages with the correct screen ids', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BusinessCaseOverview onNavigate={onNavigate} />);

    const nav = screen.getByRole('navigation', { name: 'Business case pages' });
    expect(nav).toBeInTheDocument();
    expect(within(nav).getByText('Overview').closest('[aria-current="page"]')).not.toBeNull();

    for (const page of ['data', 'infrastructure', 'features', 'controls', 'rubric']) {
      const label = { data: 'Data', infrastructure: 'Infrastructure', features: 'Features', controls: 'Controls', rubric: 'Rubric plan' }[page]!;
      await user.click(within(nav).getByRole('button', { name: label }));
      expect(onNavigate).toHaveBeenLastCalledWith(EXPECTED_SCREEN_IDS[page]);
    }
  });

  it('keeps heading order and landmarks', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    expectHeadingOrder(container);
    expect(container.querySelector('header')).not.toBeNull();
    expect(screen.getByRole('navigation', { name: 'Business case pages' })).toBeInTheDocument();
  });

  it('never calls fetch', () => {
    const fetchSpy = vi.fn(() => {
      throw new Error('business case pages must not call fetch');
    });
    vi.stubGlobal('fetch', fetchSpy);
    render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe('architecture diagram figure', () => {
  it('renders heading, caption, every statusNote and as-of text from OVERVIEW.diagram', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    const diagram = OVERVIEW.diagram;
    expect(container.textContent).toContain(diagram.heading);
    expect(container.textContent).toContain(diagram.caption);
    for (const note of diagram.statusNotes) {
      expect(container.textContent).toContain(note);
    }
    expect(container.textContent).toContain(`Status as of ${diagram.asOf}`);
  });

  it('img alt equals diagram.alt exactly and is non-empty', () => {
    render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    const img = document.querySelector('figure img') as HTMLImageElement;
    expect(img).not.toBeNull();
    expect(img.alt).toBe(OVERVIEW.diagram.alt);
    expect(img.alt.length).toBeGreaterThan(0);
  });

  it('DOM order: executive summary < figure < key line', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    const execSummary = container.querySelector('[aria-labelledby="bc-executive-summary"]')!;
    const figure = container.querySelector('figure')!;
    const keyLine = container.querySelector('[aria-labelledby="bc-key-line"]')!;
    expect(execSummary.compareDocumentPosition(figure) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(figure.compareDocumentPosition(keyLine) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('picture has a reduced-motion source with .png srcset differing from the .gif img src', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    const picture = container.querySelector('figure picture')!;
    const source = picture.querySelector('source[media="(prefers-reduced-motion: reduce)"]') as HTMLSourceElement;
    expect(source).not.toBeNull();
    const img = picture.querySelector('img') as HTMLImageElement;
    expect(img).not.toBeNull();
    expect(source.srcset.length).toBeGreaterThan(0);
    expect(img.src.length).toBeGreaterThan(0);
    expect(source.srcset).not.toBe(img.src);
    expect(img.src).toMatch(/\.gif/);
    expect(source.srcset).toMatch(/\.png/);
  });

  it('full-size link has href equal to img src, target _blank and rel containing noopener and noreferrer', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    const img = container.querySelector('figure img') as HTMLImageElement;
    const link = container.querySelector('figure a[href]') as HTMLAnchorElement;
    expect(link).not.toBeNull();
    expect(link.href).toBe(img.src);
    expect(link.target).toBe('_blank');
    expect(link.rel).toContain('noopener');
    expect(link.rel).toContain('noreferrer');
  });

  it('heading order stays valid and figure has an accessible name', () => {
    const { container } = render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    expectHeadingOrder(container);
    const figure = container.querySelector('figure')!;
    expect(figure.getAttribute('aria-labelledby')).toBeTruthy();
    const labelId = figure.getAttribute('aria-labelledby')!;
    expect(document.getElementById(labelId)).not.toBeNull();
  });

  it('no fetch/network call when rendering the page', () => {
    const fetchSpy = vi.fn(() => {
      throw new Error('business case pages must not call fetch');
    });
    vi.stubGlobal('fetch', fetchSpy);
    render(<BusinessCaseOverview onNavigate={vi.fn()} />);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
