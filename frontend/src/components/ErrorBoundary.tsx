import { Component, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          className="mx-auto mt-16 max-w-md rounded-[var(--radius-md)] border border-negative-dim-20 bg-negative-dim-5 px-6 py-8 text-center"
        >
          <p className="text-sm font-medium text-[var(--negative)]">Something went wrong</p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            An unexpected error occurred. Reload the page to try again.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 rounded-[var(--radius-sm)] bg-[var(--danger-fill)] px-4 py-2 text-xs font-medium text-[var(--on-danger)] hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--negative)] focus-visible:ring-offset-2"
          >
            Reload page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
