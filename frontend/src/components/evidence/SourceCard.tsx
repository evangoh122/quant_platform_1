interface SourceCardProps {
  ticker?: string;
  formType?: string;
  accessionNumber?: string;
  acceptedTs?: string;
  section?: string;
  sourceUrl?: string;
  retrievalMode?: string;
}

function safeUrl(url: string | undefined): string | undefined {
  if (!url || typeof url !== 'string') return undefined;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return url;
    }
    return undefined;
  } catch {
    return undefined;
  }
}

export function SourceCard({
  ticker,
  formType,
  accessionNumber,
  acceptedTs,
  section,
  sourceUrl,
  retrievalMode,
}: SourceCardProps) {
  const validUrl = safeUrl(sourceUrl);
  return (
    <div
      data-testid="source-card"
      className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-3 text-xs"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-[var(--text-primary)]">
          {ticker ?? '—'}
        </span>
        <span className="rounded bg-[var(--surface-raised)] px-1.5 py-0.5 text-[11px] font-mono text-[var(--text-muted)]">
          {formType ?? '—'}
        </span>
      </div>
      <dl className="mt-2 space-y-1">
        <div className="flex justify-between">
          <dt className="text-[var(--text-muted)]">Accession</dt>
          <dd className="font-mono text-[var(--text-secondary)]">{accessionNumber ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-[var(--text-muted)]">Accepted</dt>
          <dd className="text-[var(--text-secondary)]">{acceptedTs ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-[var(--text-muted)]">Section</dt>
          <dd className="text-[var(--text-secondary)]">{section ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-[var(--text-muted)]">Retrieval</dt>
          <dd className="text-[var(--text-secondary)]">{retrievalMode ?? '—'}</dd>
        </div>
      </dl>
      {validUrl && (
        <a
          href={validUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block text-[var(--accent)] underline hover:text-[var(--accent-bright)]"
        >
          View source
        </a>
      )}
    </div>
  );
}