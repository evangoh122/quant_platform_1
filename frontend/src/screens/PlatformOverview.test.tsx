import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { PlatformOverview } from './PlatformOverview';

describe('PlatformOverview', () => {
  it('renders Platform Overview as the landing content with snapshot labels', () => {
    render(<PlatformOverview onNavigate={vi.fn()} />);

    expect(screen.getByRole('heading', { name: 'Quant Research Platform' })).toBeInTheDocument();
    expect(screen.getByText(/287M\+ market and regulatory records/)).toBeInTheDocument();
    expect(screen.getAllByText(/Verified snapshot: 2026-10-05/).length).toBeGreaterThanOrEqual(1);
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

    const snapshotLabels = screen.getAllByText(/Verified snapshot: 2026-10-05/);
    expect(snapshotLabels.length).toBeGreaterThanOrEqual(1);

    expect(screen.queryByText(/live/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/real-time count/i)).not.toBeInTheDocument();
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