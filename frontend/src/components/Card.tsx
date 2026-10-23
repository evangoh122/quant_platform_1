import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  actions?: ReactNode;
}

export function Card({ title, subtitle, children, actions }: CardProps) {
  return (
    <section className="min-w-0 max-w-full rounded-[var(--radius-2xl)] border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h2>}
            {subtitle && <p className="break-anywhere mt-0.5 text-xs text-[var(--text-muted)]">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
