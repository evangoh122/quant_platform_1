export interface BarDatum {
  x: number;
  y: number;
  width: number;
  height: number;
  fill?: string;
  label?: string;
}

interface BarSeriesProps {
  bars: BarDatum[];
  ariaLabel?: string;
}

export function BarSeries({ bars, ariaLabel }: BarSeriesProps) {
  return (
    <g role="img" aria-label={ariaLabel}>
      {bars.map((bar, i) => (
        <rect
          key={i}
          x={bar.x}
          y={bar.y}
          width={Math.max(bar.width, 1)}
          height={Math.max(bar.height, 0)}
          fill={bar.fill ?? 'var(--accent, #3b82f6)'}
          opacity={0.7}
        >
          {bar.label && <title>{bar.label}</title>}
        </rect>
      ))}
    </g>
  );
}