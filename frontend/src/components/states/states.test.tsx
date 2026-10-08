import { render, screen, within } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { LoadingSkeleton } from './LoadingSkeleton';
import { EmptyPanel } from './EmptyPanel';
import { ErrorPanel } from './ErrorPanel';
import { StaleDataNotice } from './StaleDataNotice';
import { SuccessToast } from './SuccessToast';

describe('State primitives', () => {
  it('renders a skeleton with semantic status role', () => {
    render(<LoadingSkeleton rows={3} />);
    const status = screen.getByRole('status', { name: 'Loading' });
    expect(status).toBeInTheDocument();
    expect(status.querySelectorAll('.animate-pulse')).toHaveLength(3);
  });

  it('renders an empty panel with semantic status role', () => {
    render(<EmptyPanel title="No data" detail="Nothing to show" />);
    const status = screen.getByRole('status', { name: 'No data' });
    expect(status).toBeInTheDocument();
    expect(screen.getByText('No data')).toBeInTheDocument();
    expect(screen.getByText('Nothing to show')).toBeInTheDocument();
  });

  it('renders an error panel with alert role', () => {
    render(<ErrorPanel title="Error" message="Something broke" onRetry={() => {}} />);
    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(within(alert).getByText('Error')).toBeInTheDocument();
    expect(within(alert).getByText('Something broke')).toBeInTheDocument();
    expect(within(alert).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('renders a stale data notice with status role', () => {
    render(<StaleDataNotice table="silver_ohlcv" detail="last refresh 2h ago" />);
    const status = screen.getByRole('status', { name: 'Stale data' });
    expect(status).toBeInTheDocument();
    expect(screen.getByText(/silver_ohlcv data may be outdated/)).toBeInTheDocument();
  });

  it('renders a success toast with live region', () => {
    render(<SuccessToast message="Saved!" onDismiss={() => {}} />);
    const toast = screen.getByRole('status');
    expect(toast).toBeInTheDocument();
    expect(toast).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByText('Saved!')).toBeInTheDocument();
  });
});