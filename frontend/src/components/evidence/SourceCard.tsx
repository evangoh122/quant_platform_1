interface SourceCardProps {
  ticker?: string;
  formType?: string;
  accessionNumber?: string;
  acceptedTs?: string;
  section?: string;
  sourceUrl?: string;
  retrievalMode?: string;
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
  return (
    <div
      data-testid="source-card"
      className="rounded-md border border-slate-200 bg-white p-3 text-xs dark:border-slate-700 dark:bg-slate-900"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-slate-800 dark:text-slate-200">
          {ticker ?? '—'}
        </span>
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-mono text-slate-600 dark:bg-slate-800 dark:text-slate-400">
          {formType ?? '—'}
        </span>
      </div>
      <dl className="mt-2 space-y-1">
        <div className="flex justify-between">
          <dt className="text-slate-500">Accession</dt>
          <dd className="font-mono text-slate-700 dark:text-slate-300">{accessionNumber ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Accepted</dt>
          <dd className="text-slate-700 dark:text-slate-300">{acceptedTs ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Section</dt>
          <dd className="text-slate-700 dark:text-slate-300">{section ?? '—'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Retrieval</dt>
          <dd className="text-slate-700 dark:text-slate-300">{retrievalMode ?? '—'}</dd>
        </div>
      </dl>
      {sourceUrl && (
        <a
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block text-blue-600 underline hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
        >
          View source
        </a>
      )}
    </div>
  );
}