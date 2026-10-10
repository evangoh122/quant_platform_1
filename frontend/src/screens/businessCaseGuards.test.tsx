import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { NAV_LINKS, SNAPSHOT } from '../data/businessCase';
import { BusinessCaseOverview } from './BusinessCaseOverview';
import { BusinessCaseData } from './BusinessCaseData';
import { BusinessCaseInfrastructure } from './BusinessCaseInfrastructure';
import { BusinessCaseFeatures } from './BusinessCaseFeatures';
import { BusinessCaseControls } from './BusinessCaseControls';
import { BusinessCaseRubric } from './BusinessCaseRubric';
import { expectStringsInDom } from '../test/contentStrings';

const __dirname = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(__dirname, '../index.css'), 'utf-8');

const SCREENS = [
  { name: 'BusinessCaseOverview', render: (onNavigate: (id: string) => void) => <BusinessCaseOverview onNavigate={onNavigate} /> },
  { name: 'BusinessCaseData', render: (onNavigate: (id: string) => void) => <BusinessCaseData onNavigate={onNavigate} /> },
  { name: 'BusinessCaseInfrastructure', render: (onNavigate: (id: string) => void) => <BusinessCaseInfrastructure onNavigate={onNavigate} /> },
  { name: 'BusinessCaseFeatures', render: (onNavigate: (id: string) => void) => <BusinessCaseFeatures onNavigate={onNavigate} /> },
  { name: 'BusinessCaseControls', render: (onNavigate: (id: string) => void) => <BusinessCaseControls onNavigate={onNavigate} /> },
  { name: 'BusinessCaseRubric', render: (onNavigate: (id: string) => void) => <BusinessCaseRubric onNavigate={onNavigate} /> },
];

describe('business case cross-page guards', () => {
  it('shows the snapshot strip with asOfLabel on all six pages', () => {
    for (const screenDef of SCREENS) {
      const { container } = render(screenDef.render(vi.fn()));
      const strip = within(container).getByRole('region', { name: 'Snapshot, not live' });
      expect(strip.textContent, screenDef.name).toContain(SNAPSHOT.asOfLabel);
      expect(strip.textContent, screenDef.name).toContain(SNAPSHOT.notLiveNote);
    }
  });

  it('renders every NAV_LINKS label on all six pages', () => {
    for (const screenDef of SCREENS) {
      const { container } = render(screenDef.render(vi.fn()));
      expectStringsInDom(container, NAV_LINKS, screenDef.name);
    }
  });

  it('no rendered page text contains AUC, 0.47 or 0.533', () => {
    for (const screenDef of SCREENS) {
      const { container } = render(screenDef.render(vi.fn()));
      const text = container.textContent ?? '';
      for (const forbidden of ['AUC', '0.47', '0.533']) {
        expect(text, `${screenDef.name} must not render ${forbidden}`).not.toContain(forbidden);
      }
    }
  });

  it('no-API guard: all six screens mount with fetch replaced by a throwing spy and never call it', () => {
    const fetchSpy = vi.fn(() => {
      throw new Error('business case pages must not call fetch');
    });
    vi.stubGlobal('fetch', fetchSpy);
    for (const screenDef of SCREENS) {
      render(screenDef.render(vi.fn()));
    }
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('status badges are never colour-only: every data-status element carries visible text', () => {
    for (const screenDef of SCREENS) {
      const { container } = render(screenDef.render(vi.fn()));
      const badges = Array.from(container.querySelectorAll('[data-status]'));
      for (const badge of badges) {
        expect(badge.textContent?.trim().length ?? 0, screenDef.name).toBeGreaterThan(0);
      }
    }
  });
});

const SOURCE_FILES = [
  'businessCaseShared.tsx',
  'BusinessCaseOverview.tsx',
  'BusinessCaseData.tsx',
  'BusinessCaseInfrastructure.tsx',
  'BusinessCaseFeatures.tsx',
  'BusinessCaseControls.tsx',
  'BusinessCaseRubric.tsx',
];

describe('business case style-token guards', () => {
  it('uses only CSS variables defined in index.css and no Tailwind opacity-suffixed var colours', () => {
    const defined = new Set(
      [...css.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((match) => match[1]),
    );
    for (const file of SOURCE_FILES) {
      const source = readFileSync(join(__dirname, file), 'utf-8');
      expect(source, `${file} must not use @theme`).not.toContain('@theme');
      expect(source, `${file} must not use bg-[var(--x)]/NN`).not.toMatch(/\[var\(--[a-z0-9-]+\)\]\/\d+/);
      for (const match of source.matchAll(/var\((--[a-z0-9-]+)\)/g)) {
        expect(defined.has(match[1]), `${file} uses undefined ${match[1]}`).toBe(true);
      }
    }
  });

  it('touch targets are covered by the 44px mobile rule in index.css', () => {
    expect(css).toMatch(/@media \(max-width: 767px\)[\s\S]*min-height: 44px/);
  });
});

describe('business case no-scores guard', () => {
  it('no rendered page contains score-like numerator patterns (e.g. "x of 15", "x/100")', () => {
    const scorePattern = /\d+\s*(\/|of|out of)\s*(15|10|6|8|5|100)\b/;
    for (const screenDef of SCREENS) {
      const { container } = render(screenDef.render(vi.fn()));
      const text = container.textContent ?? '';
      expect(text, `${screenDef.name} must not contain score-like patterns`).not.toMatch(scorePattern);
    }
  });

  it('no rendered page contains score/self-assess wording except in disclaimers', () => {
    for (const screenDef of SCREENS) {
      const { container } = render(screenDef.render(vi.fn()));
      const text = (container.textContent ?? '').toLowerCase();
      const forbidden = ['scorecard', 'self-assessed', 'self assess', 'we would score', 'expected score'];
      for (const word of forbidden) {
        expect(text, `${screenDef.name} must not contain "${word}"`).not.toContain(word);
      }
    }
  });

  it('delivery status is rendered as visible text on every page that shows it', () => {
    for (const screenDef of SCREENS) {
      const { container } = render(screenDef.render(vi.fn()));
      const badges = Array.from(container.querySelectorAll('[data-status]'));
      for (const badge of badges) {
        expect(badge.textContent?.trim().length ?? 0, `${screenDef.name} status badge must have text`).toBeGreaterThan(0);
      }
    }
  });
});

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  return [parseInt(h.substring(0, 2), 16), parseInt(h.substring(2, 4), 16), parseInt(h.substring(4, 6), 16)];
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  const [rs, gs, bs] = [r, g, b].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

function contrastRatio(fg: string, bg: string): number {
  const l1 = Math.max(relativeLuminance(hexToRgb(fg)), relativeLuminance(hexToRgb(bg)));
  const l2 = Math.min(relativeLuminance(hexToRgb(fg)), relativeLuminance(hexToRgb(bg)));
  return (l1 + 0.05) / (l2 + 0.05);
}

function parseCssVar(raw: string, name: string): string {
  const match = raw.match(new RegExp(`${name}\\s*:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`CSS variable ${name} not found`);
  return match[1];
}

describe('business case contrast pairs', () => {
  const textPrimary = parseCssVar(css, '--text-primary');
  const textSecondary = parseCssVar(css, '--text-secondary');
  const textMuted = parseCssVar(css, '--text-muted');
  const warning = parseCssVar(css, '--warning');
  const accent = parseCssVar(css, '--accent');
  const borderStrong = parseCssVar(css, '--border-strong');
  const surface = parseCssVar(css, '--surface');
  const surfaceElevated = parseCssVar(css, '--surface-elevated');
  const surfaceRaised = parseCssVar(css, '--surface-raised');

  it('text colours meet 4.5:1 on the surfaces they are used on', () => {
    for (const [fg, bg] of [
      [textPrimary, surface],
      [textPrimary, surfaceElevated],
      [textSecondary, surfaceElevated],
      [textMuted, surfaceElevated],
      [warning, surfaceElevated],
      [accent, surfaceElevated],
      [textPrimary, surfaceRaised],
    ] as [string, string][]) {
      expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('interactive borders meet 3:1 on their surfaces', () => {
    for (const [fg, bg] of [
      [borderStrong, surface],
      [borderStrong, surfaceElevated],
      [accent, surface],
    ] as [string, string][]) {
      expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(3);
    }
  });
});
