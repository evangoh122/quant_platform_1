import type { ReactNode } from 'react';

interface LegendItem {
  label: string;
  color: string;
  dashed?: boolean;
}

interface ChartFrameProps {
  title: string;
  caption?: string;
  legend?: LegendItem[];
  children: ReactNode;
  tableData?: { headers: string[]; rows: (string | number)[][] };
  width?: number;
  height?: number;
  ariaLabel?: string;
}

export function ChartFrame({
  title,
  caption,
  legend,
  children,
  tableData,
  width = 600,
  height = 200,
  ariaLabel,
}: ChartFrameProps) {
  return (
    <div>
      {legend && legend.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-3">
          {legend.map((item) => (
            <div key={item.label} className="flex items-center gap-1.5">
              <span
                className="inline-block h-0.5 w-4"
                style={{
                  backgroundColor: item.color,
                  borderTop: item.dashed ? `1.5px dashed ${item.color}` : undefined,
                  height: item.dashed ? 0 : 2,
                }}
              />
              <span className="text-xs text-slate-500 dark:text-slate-400">{item.label}</span>
            </div>
          ))}
        </div>
      )}

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label={ariaLabel ?? title}
        style={{ minWidth: 280, maxHeight: height + 20 }}
      >
        {children}
      </svg>

      {caption && (
        <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{caption}</p>
      )}

      {tableData && tableData.rows.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200">
            View data table
          </summary>
          <div className="mt-1 overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-700">
                  {tableData.headers.map((h) => (
                    <th
                      key={h}
                      className="whitespace-nowrap px-2 py-1 font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableData.rows.map((row, ri) => (
                  <tr
                    key={ri}
                    className="border-b border-slate-100 last:border-0 dark:border-slate-800"
                  >
                    {row.map((cell, ci) => (
                      <td key={ci} className="whitespace-nowrap px-2 py-1 text-slate-700 dark:text-slate-300">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}