import { describe, it, expect } from 'vitest';
import { safeHttpUrl } from './url';

describe('safeHttpUrl', () => {
  it('allows http and https URLs', () => {
    expect(safeHttpUrl('https://sec.gov/filing/1')).toBe('https://sec.gov/filing/1');
    expect(safeHttpUrl('http://sec.gov/filing/1')).toBe('http://sec.gov/filing/1');
  });

  it('rejects javascript:, data:, file: and relative URLs', () => {
    expect(safeHttpUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeHttpUrl('data:text/html,<script>alert(1)</script>')).toBeUndefined();
    expect(safeHttpUrl('file:///etc/passwd')).toBeUndefined();
    expect(safeHttpUrl('/filings/1')).toBeUndefined();
  });

  it('rejects empty, null and undefined values', () => {
    expect(safeHttpUrl('')).toBeUndefined();
    expect(safeHttpUrl(null)).toBeUndefined();
    expect(safeHttpUrl(undefined)).toBeUndefined();
  });
});
