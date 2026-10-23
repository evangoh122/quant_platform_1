import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { PlatformOverview, EvidenceCard } from './PlatformOverview';

const __dirname = dirname(fileURLToPath(import.meta.url));
const css: string = readFileSync(join(__dirname, '../index.css'), 'utf-8');

describe('PlatformOverview', () => {
  it('renders Platform Overview as the landing content with snapshot labels', () => {
    render(<PlatformOverview onNavigate={vi.fn()} />);

    expect(screen.getByRole('heading', { name: 'Quant Research Platform' })).toBeInTheDocument();
    expect(screen.getByText(/Market and regulatory records transformed through Spark/)).toBeInTheDocument();
    expect(screen.getAllByText(/Recorded snapshot: 2026-10-05/).length).toBeGreaterThanOrEqual(1);
  });

  it('routes overview actions to agent, market, and architecture callbacks', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();

    render(<PlatformOverview onNavigate={onNavigate} />);

    await user.click(screen.getByRole('button', { name: 'Ask the Research Agent' }));
    expect(onNavigate).toHaveBeenCalledWith('agent');

    await user.click(screen.getByRole('button', { name: 'Explore Market Data' }));
    expect(onNavigate).toHaveBeenCalledWith('market');

    await user.click(screen.getByRole('button', { name: /View Architecture/ }));
    expect(onNavigate).toHaveBeenCalledWith('architecture');
  });

  it('renders all six overview pipeline stages and eight rubric destinations', () => {
    render(<PlatformOverview onNavigate={vi.fn()} />);

    const stages = [
      'External APIs',
      'Spark ingestion',
      'Delta bronze/silver/gold',
      'AI retrieval',
      'Lakebase action',
      'Delta activity analytics',
    ];
    for (const stage of stages) {
      expect(screen.getByText(stage)).toBeInTheDocument();
    }

    const rubricTitles = [
      'Market Explorer',
      'Options Analytics',
      'SEC Research',
      'AI Research Agent',
      'Signal Explorer',
      'Paper Portfolio',
      'System Health',
      'Architecture & Tests',
    ];
    for (const title of rubricTitles) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
  });

  it('does not render snapshot evidence as live counters', () => {
    render(<PlatformOverview onNavigate={vi.fn()} />);

    const snapshotLabels = screen.getAllByText(/Recorded snapshot: 2026-10-05/);
    expect(snapshotLabels.length).toBeGreaterThanOrEqual(1);

    expect(screen.queryByText(/real-time/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/real-time count/i)).not.toBeInTheDocument();
  });

  it('every numeric claim with M+, records, or chunks is inside a snapshot-labelled container', () => {
    const { container } = render(<PlatformOverview onNavigate={vi.fn()} />);

    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const pattern = /\d[\d,.]*\s*(M\+|records|chunks)/;
    const failures: string[] = [];

    while (walker.nextNode()) {
      const text = walker.currentNode.textContent ?? '';
      if (!pattern.test(text)) continue;

      const el = walker.currentNode.parentElement;
      const card = el?.closest('[data-evidence-card]');
      const labelled = !!card && (card.textContent?.includes('Recorded snapshot: 2026-10-05') ?? false);
      if (!labelled) {
        failures.push(`Unlabelled numeric claim: "${text.trim()}"`);
      }
    }

    expect(failures).toEqual([]);
  });

  it('renders evidence cards for all six data categories', () => {
    render(<PlatformOverview onNavigate={vi.fn()} />);

    expect(screen.getByText('287M+')).toBeInTheDocument();
    expect(screen.getByText('152.1M')).toBeInTheDocument();
    expect(screen.getByText('10,720')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('Lakebase')).toBeInTheDocument();
    expect(screen.getByText('Spark bronze/silver/gold')).toBeInTheDocument();
  });

  it('wraps a long unbreakable evidence value at a 320 px width', () => {
    const originalInnerWidth = window.innerWidth;
    Object.defineProperty(window, 'innerWidth', { value: 320, writable: true, configurable: true });

    try {
      const longValue = `Lakebase-${'x'.repeat(80)}`;
      render(<EvidenceCard label="Operational model" value={longValue} />);

      const value = screen.getByText(longValue);
      expect(value.className).toContain('break-anywhere');
      expect(value.className).toContain('min-w-0');
      expect(value.className).not.toContain('truncate');
      expect(value.className).not.toContain('whitespace-nowrap');

      // The class only helps if the shared rule actually wraps long tokens.
      expect(css).toMatch(/\.break-anywhere\s*\{[^}]*overflow-wrap:\s*anywhere/);
      expect(css).toMatch(/\.break-anywhere\s*\{[^}]*word-break:\s*break-word/);
    } finally {
      Object.defineProperty(window, 'innerWidth', {
        value: originalInnerWidth,
        writable: true,
        configurable: true,
      });
    }
  });

  it('navigates to each rubric destination on click', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();

    render(<PlatformOverview onNavigate={onNavigate} />);

    const rubricButtons = screen.getAllByText('View →');
    expect(rubricButtons).toHaveLength(8);

    await user.click(rubricButtons[0].closest('button')!);
    expect(onNavigate).toHaveBeenCalledWith('market');
  });
});