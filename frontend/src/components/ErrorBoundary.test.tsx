import type { ReactElement } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

function Boom(): ReactElement {
  throw new Error('secret stack detail');
}

describe('ErrorBoundary', () => {
  let errorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    errorSpy.mockRestore();
  });

  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <p>content</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText('content')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows an accessible alert with a reload button when a child throws', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/something went wrong/i);
    expect(screen.getByRole('button', { name: /reload page/i })).toBeInTheDocument();
  });

  it('does not leak the thrown error or its stack', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    const text = document.body.textContent ?? '';
    expect(text).not.toContain('secret stack detail');
    expect(text).not.toContain('Boom');
    expect(text).not.toContain('at ');
  });

  it('reloads the page when the button is clicked', () => {
    const originalLocation = window.location;
    const reload = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, reload },
    });
    try {
      render(
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>,
      );
      fireEvent.click(screen.getByRole('button', { name: /reload page/i }));
      expect(reload).toHaveBeenCalledTimes(1);
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: originalLocation,
      });
    }
  });
});
