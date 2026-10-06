import type { ScaleDomain, ScaleRange } from './scales';
import { linearScale, tickValues } from './scales';

interface XAxisProps {
  domain: ScaleDomain;
  range: ScaleRange;
  y: number;
  labels?: string[];
  tickCount?: number;
}

export function XAxis({ domain, range, y, labels, tickCount = 5 }: XAxisProps) {
  const scale = linearScale(domain, range);
  const ticks = labels
    ? labels.map((l, i) => ({
        x: range.start + ((i + 0.5) / labels.length) * (range.end - range.start),
        label: l,
      }))
    : tickValues(domain.min, domain.max, tickCount).map((v) => ({
        x: scale(v),
        label: v.toFixed(0),
      }));

  return (
    <g>
      <line
        x1={range.start}
        y1={y}
        x2={range.end}
        y2={y}
        stroke="currentColor"
        strokeOpacity={0.2}
      />
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={t.x} y1={y} x2={t.x} y2={y + 4} stroke="currentColor" strokeOpacity={0.2} />
          <text
            x={t.x}
            y={y + 14}
            textAnchor="middle"
            className="fill-slate-400 dark:fill-slate-500"
            style={{ fontSize: 9 }}
          >
            {t.label}
          </text>
        </g>
      ))}
    </g>
  );
}

interface YAxisProps {
  domain: ScaleDomain;
  range: ScaleRange;
  x: number;
  tickCount?: number;
  format?: (v: number) => string;
}

export function YAxis({ domain, range, x, tickCount = 5, format }: YAxisProps) {
  const scale = linearScale(domain, range);
  const ticks = tickValues(domain.min, domain.max, tickCount);

  return (
    <g>
      <line
        x1={x}
        y1={range.start}
        x2={x}
        y2={range.end}
        stroke="currentColor"
        strokeOpacity={0.2}
      />
      {ticks.map((v, i) => {
        const y = scale(v);
        return (
          <g key={i}>
            <line x1={x - 4} y1={y} x2={x} y2={y} stroke="currentColor" strokeOpacity={0.2} />
            <text
              x={x - 6}
              y={y + 3}
              textAnchor="end"
              className="fill-slate-400 dark:fill-slate-500"
              style={{ fontSize: 9 }}
            >
              {format ? format(v) : v.toFixed(1)}
            </text>
          </g>
        );
      })}
    </g>
  );
}