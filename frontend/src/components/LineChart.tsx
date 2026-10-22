import { useMemo } from 'react';

export interface LineChartSeries {
  key: string;
  label: string;
  /** `[ISO date, value]` pairs, already aligned by the API. */
  points: [string, number][];
  /** CSS custom-property name (theme token), e.g. `--accent`. */
  colorVar?: string;
  dashed?: boolean;
}

interface LineChartProps {
  series: LineChartSeries[];
  ariaLabel: string;
  /** Visually hidden sentence read by screen readers. */
  summary: string;
  unit?: string;
  formatter?: (value: number) => string;
}

const WIDTH = 640;
const HEIGHT = 220;
const PADDING = { top: 10, right: 64, bottom: 28, left: 40 };

function colour(series: LineChartSeries): string {
  return `var(${series.colorVar ?? '--accent'})`;
}

function formatDay(iso: string): string {
  try {
    return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

/**
 * Hand-drawn SVG line chart (the app has no chart library). The API supplies
 * dates and values; this component computes only screen coordinates. Series are
 * distinguished by colour AND dash pattern/legend, never by colour alone.
 */
export function LineChart({ series, ariaLabel, summary, unit, formatter }: LineChartProps) {
  const dates = useMemo(
    () => Array.from(new Set(series.flatMap((s) => s.points.map((p) => p[0])))).sort(),
    [series],
  );

  const shape = useMemo(() => {
    const values = series
      .flatMap((s) => s.points.map((p) => p[1]))
      .filter((v) => Number.isFinite(v));
    if (values.length === 0) return null;
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const span = rawMax - rawMin || Math.max(Math.abs(rawMax), 1);
    const min = rawMin - span * 0.05;
    const max = rawMax + span * 0.05;
    return { min, max, span: max - min };
  }, [series]);

  if (!shape || dates.length < 2) return null;

  const chartW = WIDTH - PADDING.left - PADDING.right;
  const chartH = HEIGHT - PADDING.top - PADDING.bottom;
  const show = (value: number) => (formatter ? formatter(value) : value.toFixed(2));

  const xForIndex = (index: number) => PADDING.left + (index / (dates.length - 1)) * chartW;
  const xForDate = (iso: string) => xForIndex(dates.indexOf(iso));
  const yForValue = (value: number) =>
    PADDING.top + chartH - ((value - shape.min) / shape.span) * chartH;

  const tickIndices =
    dates.length <= 4
      ? dates.map((_, i) => i)
      : [0, Math.floor((dates.length - 1) / 3), Math.floor((2 * (dates.length - 1)) / 3), dates.length - 1];

  return (
    <div>
      {series.length > 1 && (
        <ul className="mb-1 flex flex-wrap gap-3 text-xs text-[var(--text-secondary)]">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1">
              <svg width={18} height={6} aria-hidden="true">
                <line
                  x1={0}
                  y1={3}
                  x2={18}
                  y2={3}
                  stroke={colour(s)}
                  strokeWidth={2}
                  strokeDasharray={s.dashed ? '5 3' : undefined}
                />
              </svg>
              <span>{s.label}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="w-full"
          role="img"
          aria-label={ariaLabel}
          style={{ minWidth: 300, maxHeight: 240 }}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
            const y = PADDING.top + chartH * (1 - frac);
            const value = shape.min + shape.span * frac;
            return (
              <g key={frac}>
                <line
                  x1={PADDING.left}
                  y1={y}
                  x2={WIDTH - PADDING.right}
                  y2={y}
                  stroke="currentColor"
                  strokeOpacity={0.08}
                />
                <text
                  x={PADDING.left - 4}
                  y={y + 3}
                  textAnchor="end"
                  style={{ fontSize: 9, fill: 'var(--text-muted)' }}
                >
                  {show(value)}
                </text>
              </g>
            );
          })}

          {series.map((s) => {
            const path = s.points
              .map(([date, value], i) => {
                const x = xForDate(date);
                const y = yForValue(value);
                return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
              })
              .join(' ');
            return (
              <path
                key={s.key}
                d={path}
                fill="none"
                stroke={colour(s)}
                strokeWidth={1.6}
                strokeDasharray={s.dashed ? '5 3' : undefined}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            );
          })}

          {/* Direct end labels (not hover-only) */}
          {series.map((s) => {
            const last = s.points[s.points.length - 1];
            if (!last) return null;
            return (
              <text
                key={`end-${s.key}`}
                x={xForDate(last[0]) + 4}
                y={yForValue(last[1]) + 3}
                style={{ fontSize: 9, fill: colour(s) }}
              >
                {show(last[1])}
              </text>
            );
          })}

          {tickIndices.map((index) => (
            <text
              key={`tick-${index}`}
              x={xForIndex(index)}
              y={HEIGHT - 5}
              textAnchor="middle"
              style={{ fontSize: 9, fill: 'var(--text-muted)' }}
            >
              {formatDay(dates[index])}
            </text>
          ))}

          {unit ? (
            <text
              x={WIDTH - PADDING.right + 4}
              y={PADDING.top + 8}
              style={{ fontSize: 9, fill: 'var(--text-muted)' }}
            >
              {unit}
            </text>
          ) : null}
        </svg>
      </div>

      <p className="sr-only">{summary}</p>
    </div>
  );
}
