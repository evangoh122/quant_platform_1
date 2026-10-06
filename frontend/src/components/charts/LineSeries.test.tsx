import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { LineSeries } from './LineSeries';

function renderLine(data: (number | null)[]) {
  const points = data.map((y) => ({ x: 0, y }));
  const getX = (i: number) => i * 100;
  const getY = (v: number) => 200 - v * 10;
  const { container } = render(
    <svg>
      <LineSeries data={points} getX={getX} getY={getY} ariaLabel="test line" />
    </svg>,
  );
  return container;
}

describe('LineSeries', () => {
  it('renders 2 path segments for [1, null, 3]', () => {
    const container = renderLine([1, null, 3]);
    const paths = container.querySelectorAll('path');
    expect(paths.length).toBe(2);
  });

  it('renders 1 continuous path when no nulls', () => {
    const container = renderLine([1, 2, 3]);
    const paths = container.querySelectorAll('path');
    expect(paths.length).toBe(1);
  });

  it('renders 0 paths when all null', () => {
    const container = renderLine([null, null, null]);
    const paths = container.querySelectorAll('path');
    expect(paths.length).toBe(0);
  });

  it('creates a gap at null, not a zero point', () => {
    const container = renderLine([1, null, 3]);
    const paths = container.querySelectorAll('path');
    // First path should end at y=190 (200 - 1*10)
    const d1 = paths[0].getAttribute('d')!;
    expect(d1).toContain('190.0');
    // Second path should start at y=170 (200 - 3*10)
    const d2 = paths[1].getAttribute('d')!;
    expect(d2).toContain('170.0');
    // Neither path should contain y=200 (which would be the 0 value)
    expect(d1).not.toContain(',200.0');
    expect(d2).not.toContain(',200.0');
  });

  it('renders 3 segments for [1, null, 2, null, 3]', () => {
    const container = renderLine([1, null, 2, null, 3]);
    const paths = container.querySelectorAll('path');
    expect(paths.length).toBe(3);
  });
});