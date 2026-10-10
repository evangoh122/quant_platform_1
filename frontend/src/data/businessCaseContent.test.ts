import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect } from 'vitest';
import {
  CONTROLS,
  DATA,
  EXECUTIVE_SUMMARY,
  FEATURES,
  KEY_LINE,
  NEXT_APPROACH,
  NAV_LINKS,
  OVERVIEW,
  SNAPSHOT,
} from './businessCase';

const __dirname = dirname(fileURLToPath(import.meta.url));

const PINNED_SHA256 = 'e4671600967bbe28dd02ca28a5ca02c9058e13cf2b37b54f71c59124f776e60f';

describe('business case content lock', () => {
  it('frontend/src/data/businessCase.ts matches the pinned SHA-256 (copy changes require Sol+Opus re-authoring and re-pinning)', () => {
    const bytes = readFileSync(join(__dirname, 'businessCase.ts'));
    const digest = createHash('sha256').update(bytes).digest('hex');
    expect(
      digest,
      'businessCase.ts copy is owner-directed and locked; re-author with Sol+Opus and re-pin before changing it',
    ).toBe(PINNED_SHA256);
  });
});

describe('business case doc fidelity', () => {
  const businessDoc = readFileSync(join(__dirname, '../../../docs/BUSINESS_CASE.md'), 'utf-8');
  const quantDoc = readFileSync(join(__dirname, '../../../docs/QUANT_STRATEGIES.md'), 'utf-8');

  const POINTER = /[A-Za-z0-9_./-]+\.(?:py|sql|md|tsx|ts|yml|yaml|json|txt|cfg|html|sh)(?::[\d,\-]+)?/g;
  const NUMBER = /\d+(?:,\d{3})*(?:\.\d+)?/g;

  it('every number in the content that is not a file pointer appears verbatim in BUSINESS_CASE.md or, for 1977 and 1989, in QUANT_STRATEGIES.md', () => {
    const failures: string[] = [];
    let checked = 0;

    const visit = (node: unknown, path: string): void => {
      if (typeof node === 'number') {
        checked += 1;
        const token = String(node);
        if (!businessDoc.includes(token)) failures.push(`${path}: ${token}`);
        return;
      }
      if (typeof node === 'string') {
        const stripped = node.replace(POINTER, ' ');
        for (const match of stripped.matchAll(NUMBER)) {
          checked += 1;
          const token = match[0];
          const source = token === '1977' || token === '1989' ? quantDoc : businessDoc;
          if (!source.includes(token)) failures.push(`${path}: ${token}`);
        }
        return;
      }
      if (Array.isArray(node)) {
        node.forEach((item, index) => visit(item, `${path}[${index}]`));
      } else if (node !== null && typeof node === 'object') {
        for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
          visit(value, `${path}.${key}`);
        }
      }
    };

    visit(
      { SNAPSHOT, EXECUTIVE_SUMMARY, KEY_LINE, OVERVIEW, DATA, FEATURES, CONTROLS, NEXT_APPROACH, NAV_LINKS },
      '$',
    );

    expect(checked).toBeGreaterThan(20);
    expect(failures).toEqual([]);
  });

  it('the study years 1977 and 1989 are quoted from QUANT_STRATEGIES.md', () => {
    expect(quantDoc).toContain('1977');
    expect(quantDoc).toContain('1989');
  });
});
