import { describe, it, expect } from 'vitest';
import { formatNumber } from './number';

describe('formatNumber', () => {
  it('formats finite numbers with the requested digits', () => {
    expect(formatNumber(1234.567)).toBe('1234.57');
    expect(formatNumber(1.23456, 4)).toBe('1.2346');
    expect(formatNumber(0)).toBe('0.00');
  });

  it('returns an em dash for null, undefined, NaN and Infinity', () => {
    expect(formatNumber(null)).toBe('\u2014');
    expect(formatNumber(undefined)).toBe('\u2014');
    expect(formatNumber(Number.NaN)).toBe('\u2014');
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe('\u2014');
  });
});
