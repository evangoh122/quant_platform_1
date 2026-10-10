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
  INFRASTRUCTURE,
  KEY_LINE,
  NEXT_APPROACH,
  NAV_LINKS,
  OVERVIEW,
  RUBRIC_AI,
  SNAPSHOT,
} from './businessCase';

const __dirname = dirname(fileURLToPath(import.meta.url));

const PINNED_SHA256 = 'a1e11de2136d466d91022e818726fbd8a4d81ad3d20fee9ddf5d2cc21ee74912';

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
  const tsvDoc = readFileSync(join(__dirname, '../../../docs/proposal/row_counts_2026-10-05.tsv'), 'utf-8');
  const readmeDoc = readFileSync(join(__dirname, '../../../README.md'), 'utf-8');
  let goldSql = '';
  try {
    goldSql = readFileSync(join(__dirname, '../../../gold/05_gold_model_features.sql'), 'utf-8');
  } catch {
    // If gold file not found, fall back to universe.yaml count check
    try {
      goldSql = readFileSync(join(__dirname, '../../../config/universe.yaml'), 'utf-8');
    } catch {
      // Neither file available
    }
  }

  const POINTER = /[A-Za-z0-9_./-]+\.(?:py|sql|md|tsx|ts|yml|yaml|json|txt|cfg|html|sh)(?::[\d,\-]+)?/g;
  const NUMBER = /\d+(?:,\d{3})*(?:\.\d+)?/g;

  it('every number in the content that is not a file pointer appears verbatim in the docs', () => {
    const failures: string[] = [];
    let checked = 0;

    const allSources = [businessDoc, quantDoc, tsvDoc, readmeDoc, goldSql].join('\n');

    const visit = (node: unknown, path: string): void => {
      if (typeof node === 'number') {
        checked += 1;
        const token = String(node);
        if (!allSources.includes(token)) failures.push(`${path}: ${token}`);
        return;
      }
      if (typeof node === 'string') {
        const stripped = node.replace(POINTER, ' ');
        for (const match of stripped.matchAll(NUMBER)) {
          checked += 1;
          const token = match[0];
          if (!allSources.includes(token)) failures.push(`${path}: ${token}`);
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
      { SNAPSHOT, EXECUTIVE_SUMMARY, KEY_LINE, OVERVIEW, DATA, FEATURES, CONTROLS, NEXT_APPROACH, INFRASTRUCTURE, RUBRIC_AI, NAV_LINKS },
      '$',
    );

    expect(checked).toBeGreaterThan(20);
    expect(failures).toEqual([]);
  });

  it('the study years 1977 and 1989 are quoted from QUANT_STRATEGIES.md', () => {
    expect(quantDoc).toContain('1977');
    expect(quantDoc).toContain('1989');
  });

  it('rubric pointsPossible values equal [15,10,15,6,8,6,10,10,5,5,5,5] and sum to 100', () => {
    const expected = [15, 10, 15, 6, 8, 6, 10, 10, 5, 5, 5, 5];
    const actual = RUBRIC_AI.planAndDelivery.rows.map((r) => r.pointsPossible);
    expect(actual).toEqual(expected);
    expect(actual.reduce((a, b) => a + b, 0)).toBe(100);
  });

  it('rubric category groupings sum to the rubric category totals (15,10,15,20,10,10,5,15)', () => {
    const rows = RUBRIC_AI.planAndDelivery.rows;
    const spark = rows.find((r) => r.id === 'spark')!.pointsPossible;
    const api = rows.find((r) => r.id === 'api')!.pointsPossible;
    const lakebase = rows.find((r) => r.id === 'lakebase')!.pointsPossible;
    const agentRead = rows.find((r) => r.id === 'agent-read')!.pointsPossible;
    const agentWrite = rows.find((r) => r.id === 'agent-write')!.pointsPossible;
    const agentQuality = rows.find((r) => r.id === 'agent-quality')!.pointsPossible;
    const analytics = rows.find((r) => r.id === 'analytics')!.pointsPossible;
    const frontend = rows.find((r) => r.id === 'frontend')!.pointsPossible;
    const deployment = rows.find((r) => r.id === 'deployment')!.pointsPossible;
    const volume = rows.find((r) => r.id === 'volume')!.pointsPossible;
    const velocity = rows.find((r) => r.id === 'velocity')!.pointsPossible;
    const variety = rows.find((r) => r.id === 'variety')!.pointsPossible;

    expect(spark).toBe(15);
    expect(api).toBe(10);
    expect(lakebase).toBe(15);
    expect(agentRead + agentWrite + agentQuality).toBe(20);
    expect(analytics).toBe(10);
    expect(frontend).toBe(10);
    expect(deployment).toBe(5);
    expect(volume + velocity + variety).toBe(15);
  });

  it('the content module contains none of the removed score fields in its exported data', () => {
    const removed = ['selfAssessedBand', 'totals', 'evidenceStrength', 'swingFactors', 'scorecard'];
    const rubricJson = JSON.stringify(RUBRIC_AI);
    for (const field of removed) {
      expect(rubricJson, `RUBRIC_AI must not contain removed field: ${field}`).not.toContain(field);
    }
  });
});
