const EM_DASH = '\u2014';

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null || typeof value !== 'number' || !Number.isFinite(value)) return EM_DASH;
  return value.toFixed(digits);
}
