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

/**
 * Chart geometry, following the rule `MarketDashboard` set for the type floor.
 *
 * The plot is authored in a 640 x 220 viewBox, so SVG user units only equal CSS
 * pixels while the SVG renders at or above its viewBox width. The wrapper
 * scrolls horizontally instead of shrinking below `LINE_CHART_MIN_RENDER_WIDTH`,
 * which equals the viewBox width, so the render scale is never below 1 and the
 * 12-unit labels always paint at >= 12 px (the HIG legibility floor). A floor of
 * `min-width: 300` against this viewBox used to scale every label to 4.22 px at
 * any viewport. `layout-overflow.test.tsx` re-derives this ratio from the
 * rendered DOM.
 */
export const LINE_CHART_VIEW_WIDTH = 640;
export const LINE_CHART_VIEW_HEIGHT = 220;
export const LINE_CHART_MIN_RENDER_WIDTH = LINE_CHART_VIEW_WIDTH;
export const LINE_CHART_FONT_SIZE = 12;

/**
 * Insets leave room for 12-unit text so no label is clipped by the viewBox:
 * 60 units left of the y-axis labels and 68 units right of the last point,
 * each enough for eight characters.
 */
const PADDING = { top: 14, right: 72, bottom: 30, left: 64 };

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

  const chartW = LINE_CHART_VIEW_WIDTH - PADDING.left - PADDING.right;
  const chartH = LINE_CHART_VIEW_HEIGHT - PADDING.top - PADDING.bottom;
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
          viewBox={`0 0 ${LINE_CHART_VIEW_WIDTH} ${LINE_CHART_VIEW_HEIGHT}`}
          className="w-full"
          role="img"
          aria-label={ariaLabel}
          // The plot keeps a legible 12 px floor: at any width the SVG renders
          // at or above its 640-unit viewBox, so a 12-unit label is never
          // smaller than 12 CSS px; narrower wrappers scroll horizontally
          // instead of shrinking the labels into illegibility (HIG
          // typography.md minimum sizes).
          style={{ minWidth: LINE_CHART_MIN_RENDER_WIDTH, maxHeight: 240 }}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
            const y = PADDING.top + chartH * (1 - frac);
            const value = shape.min + shape.span * frac;
            return (
              <g key={frac}>
                <line
                  x1={PADDING.left}
                  y1={y}
                  x2={LINE_CHART_VIEW_WIDTH - PADDING.right}
                  y2={y}
                  stroke="currentColor"
                  strokeOpacity={0.08}
                />
                <text
                  x={PADDING.left - 4}
                  y={y + 4}
                  textAnchor="end"
                  style={{ fontSize: LINE_CHART_FONT_SIZE, fill: 'var(--text-muted)' }}
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
                y={yForValue(last[1]) + 4}
                style={{ fontSize: LINE_CHART_FONT_SIZE, fill: colour(s) }}
              >
                {show(last[1])}
              </text>
            );
          })}

          {tickIndices.map((index) => (
            <text
              key={`tick-${index}`}
              x={xForIndex(index)}
              y={LINE_CHART_VIEW_HEIGHT - 5}
              textAnchor="middle"
              style={{ fontSize: LINE_CHART_FONT_SIZE, fill: 'var(--text-muted)' }}
            >
              {formatDay(dates[index])}
            </text>
          ))}

          {unit ? (
            <text
              x={LINE_CHART_VIEW_WIDTH - PADDING.right + 4}
              y={PADDING.top + 10}
              style={{ fontSize: LINE_CHART_FONT_SIZE, fill: 'var(--text-muted)' }}
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
