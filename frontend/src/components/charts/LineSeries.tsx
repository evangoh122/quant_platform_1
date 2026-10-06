import { useMemo } from 'react';

export interface DataPoint {
  x: number;
  y: number | null;
}

interface LineSeriesProps {
  data: DataPoint[];
  getX: (i: number) => number;
  getY: (v: number) => number;
  stroke?: string;
  strokeWidth?: number;
  ariaLabel?: string;
}

export function LineSeries({
  data,
  getX,
  getY,
  stroke = 'var(--accent, #3b82f6)',
  strokeWidth = 1.5,
  ariaLabel,
}: LineSeriesProps) {
  const segments = useMemo(() => {
    const result: string[] = [];
    let current = '';
    for (let i = 0; i < data.length; i++) {
      const pt = data[i];
      if (pt.y == null) {
        if (current) {
          result.push(current);
          current = '';
        }
        continue;
      }
      const cmd = current === '' ? 'M' : 'L';
      current += `${cmd}${getX(i).toFixed(1)},${getY(pt.y).toFixed(1)}`;
    }
    if (current) result.push(current);
    return result;
  }, [data, getX, getY]);

  return (
    <g role="img" aria-label={ariaLabel}>
      {segments.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="none"
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ))}
    </g>
  );
}