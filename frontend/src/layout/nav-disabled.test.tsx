import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import App from '../App';

const __dirname = dirname(fileURLToPath(import.meta.url));
const css: string = readFileSync(join(__dirname, '../index.css'), 'utf-8');

const healthyResponse = {
  status: 'ok',
  version: '1.0.0',
  dependencies: [
    { name: 'lakebase', ok: true, detail: 'connected', latency_ms: 5, last_error: null, last_ok_at: Date.now(), circuit_breaker_state: null },
  ],
  freshness: { state: 'fresh', table: '', detail: '' },
  role_cache_size: 0,
  startup: [],
};

function mockFetch() {
  return vi.fn().mockImplementation((url: string) => {
    if (url === '/api/health') return Promise.resolve({ ok: true, json: () => Promise.resolve(healthyResponse) });
    if (url === '/api/health/trace') return Promise.resolve({ ok: true, json: () => Promise.resolve({ slow: [] }) });
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

const COMING_SOON_ITEMS = ['Quant Research Project', 'Prediction Markets Analysis'];

function hintFor(button: HTMLElement): string {
  const id = button.getAttribute('aria-describedby');
  expect(id).toBeTruthy();
  return document.getElementById(id as string)?.textContent ?? '';
}

function matchMedia(query: string): MediaQueryList {
  return {
    matches: query.includes('prefers-reduced-motion'),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  } as MediaQueryList;
}

describe('Greyed-out placeholder navigation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Keep the auto-starting product tour out of these interaction tests: it
    // opens after 600 ms and would steal focus mid-assertion.
    vi.stubGlobal('matchMedia', matchMedia);
  });

  it('styles disabled nav items with muted text, reduced opacity and a not-allowed cursor', () => {
    expect(css).toMatch(/\.nav-item\.nav-item-disabled[\s\S]*?color:\s*var\(--text-muted\)/);
    expect(css).toMatch(/\.nav-item\.nav-item-disabled[\s\S]*?cursor:\s*not-allowed/);
    expect(css).toMatch(/\.nav-item\.nav-item-disabled[\s\S]*?opacity:\s*0?\.\d+/);
  });

  it('renders aria-disabled, non-navigating items with a keyboard hint in the desktop sidebar', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = userEvent.setup();

    render(<App />);

    const overviewHeading = await screen.findByRole('heading', { name: 'Platform Overview' });
    const sidebar = screen.getByRole('complementary');

    for (const label of COMING_SOON_ITEMS) {
      const button = within(sidebar).getByRole('button', { name: new RegExp(label) });
      expect(button).toHaveAttribute('aria-disabled', 'true');
      expect(button).not.toHaveAttribute('disabled');
      expect(button).toHaveClass('nav-item-disabled');
      expect(hintFor(button)).toBe('Coming soon');

      // Keyboard reachable, so the hint is announced rather than title-only.
      button.focus();
      expect(button).toHaveFocus();

      await user.click(button);
      await user.keyboard('{Enter}');
      await user.keyboard(' ');

      expect(overviewHeading).toBeInTheDocument();
      expect(button).not.toHaveAttribute('aria-current');
    }
  });

  it('renders aria-disabled, non-navigating items with a keyboard hint in the mobile drawer', async () => {
    vi.stubGlobal('fetch', mockFetch());
    const user = userEvent.setup();
    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });

    render(<App />);

    const overviewHeading = await screen.findByRole('heading', { name: 'Platform Overview' });
    await user.click(screen.getByLabelText('Open navigation'));

    const dialog = screen.getByRole('dialog', { name: 'Navigation' });

    for (const label of COMING_SOON_ITEMS) {
      const button = within(dialog).getByRole('button', { name: new RegExp(label) });
      expect(button).toHaveAttribute('aria-disabled', 'true');
      expect(hintFor(button)).toBe('Coming soon');

      await user.click(button);

      // No navigation means the drawer stays open and the screen is unchanged.
      expect(screen.getByRole('dialog', { name: 'Navigation' })).toBeInTheDocument();
      expect(overviewHeading).toBeInTheDocument();
      expect(button).not.toHaveAttribute('aria-current');
    }
  });

  it('places the placeholders in the Strategy group next to Strategy Lab', async () => {
    vi.stubGlobal('fetch', mockFetch());

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Platform Overview' })).toBeInTheDocument();
    });

    const sidebar = screen.getByRole('complementary');
    const buttons = within(sidebar).getAllByRole('button').map((b) => b.textContent);
    const strategyLab = buttons.indexOf('Strategy Lab');
    expect(strategyLab).toBeGreaterThanOrEqual(0);
    expect(buttons[strategyLab + 1]).toBe('Quant Research Project');
    expect(buttons[strategyLab + 2]).toBe('Prediction Markets Analysis');
  });
});
