import { useState } from 'react';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import CoachMarks, { type CoachStep } from './CoachMarks';

// ---------- helpers ----------

function setViewport(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', { value: width, writable: true });
  Object.defineProperty(window, 'innerHeight', { value: height, writable: true });
}

function fakeRect(overrides: Partial<DOMRect> = {}): DOMRect {
  return {
    top: 100, left: 100, width: 200, height: 50, bottom: 150, right: 300,
    x: 100, y: 100, toJSON: () => {},
    ...overrides,
  } as DOMRect;
}

function mockReducedMotion() {
  const original = window.matchMedia;
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === '(prefers-reduced-motion: reduce)',
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
  return () => { window.matchMedia = original; };
}

// =====================================================================
// TEST 1: Fix 2 — Waiting-branch deferred measure timer is cancelled on close
// =====================================================================

describe('r13 Fix 2: waiting-branch deferred measure is cancelled on close', () => {
  const cleanupEls: HTMLElement[] = [];

  afterEach(() => {
    cleanupEls.forEach((el) => { if (el.parentNode) el.parentNode.removeChild(el); });
    cleanupEls.length = 0;
    vi.useRealTimers();
  });

  it('closing within 280ms of target resolving does not run stale measure', async () => {
    vi.useFakeTimers();
    setViewport(1024, 768);

    const measureSpy = vi.fn().mockReturnValue(
      fakeRect({ left: 200, top: 200, width: 100, height: 50 }),
    );

    const steps: CoachStep[] = [
      {
        selector: '[data-tour="r13-late-cancel"]',
        title: 'Late Cancel',
        body: 'Test',
        waitForTargetTimeout: 5000,
      },
    ];

    function Harness() {
      const [run, setRun] = useState(true);
      return (
        <div>
          <CoachMarks
            steps={steps}
            run={run}
            onClose={() => setRun(false)}
          />
        </div>
      );
    }

    render(<Harness />);

    // Should be in waiting state (target absent at mount)
    expect(screen.getByText('Waiting for screen to load...')).toBeInTheDocument();

    // Record timer count before inserting target
    const timersBefore = vi.getTimerCount();

    // Insert target — MutationObserver will fire on next microtask
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'r13-late-cancel');
    targetEl.getBoundingClientRect = measureSpy;
    targetEl.scrollIntoView = () => {};
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    // Flush MutationObserver callback (microtask) + resolveTarget scheduling
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Waiting state should be resolved now
    expect(screen.queryByText('Waiting for screen to load...')).not.toBeInTheDocument();

    // resolveTarget scheduled setTimeout(measure, 280) — close before it fires
    fireEvent.keyDown(window, { key: 'Escape' });

    // Tour should close; cleanup runs and clears measureTimer
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    // Record getBoundingClientRect calls so far
    const callsBeforeAdvance = measureSpy.mock.calls.length;

    // Advance past the 280 ms deferred-measure window.
    // If measureTimer was NOT cleared, measure() fires and calls getBoundingClientRect.
    act(() => { vi.advanceTimersByTime(300); });

    // No new getBoundingClientRect calls — stale measure never ran
    expect(measureSpy.mock.calls.length).toBe(callsBeforeAdvance);
  });
});

// =====================================================================
// TEST 2: Reduced-motion per-call-site mutation proofs
// =====================================================================

describe('r13 Reduced-motion: per-call-site mutation proofs', () => {
  const cleanupEls: HTMLElement[] = [];

  afterEach(() => {
    cleanupEls.forEach((el) => { if (el.parentNode) el.parentNode.removeChild(el); });
    cleanupEls.length = 0;
    vi.useRealTimers();
  });

  // --- F2a: immediate branch (line 131) ---
  it('immediate-target scroll uses behavior "auto" under prefers-reduced-motion (line 131 mutation proof)', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);
    const restoreMatchMedia = mockReducedMotion();

    const scrollIntoViewSpy = vi.fn();
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'r13-immediate-motion');
    targetEl.scrollIntoView = scrollIntoViewSpy;
    // On-screen so measure() does NOT call scrollIntoView at line 89
    targetEl.getBoundingClientRect = () => fakeRect();
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    const steps: CoachStep[] = [
      { selector: '[data-tour="r13-immediate-motion"]', title: 'Immediate', body: 'Test' },
    ];

    render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    // The immediate branch fires synchronously in useLayoutEffect (line 131).
    // Its call carries inline: 'nearest', which distinguishes it from line 89.
    const immediateCall = scrollIntoViewSpy.mock.calls.find(
      (call: unknown[]) => (call[0] as Record<string, unknown>)?.inline === 'nearest',
    );
    expect(immediateCall).toBeTruthy();
    expect((immediateCall![0] as Record<string, unknown>).behavior).toBe('auto');

    restoreMatchMedia();
  });

  // --- F2b: measure re-scroll (line 89) ---
  it('measure off-screen re-scroll uses behavior "auto" under prefers-reduced-motion (line 89 mutation proof)', () => {
    vi.useFakeTimers();
    setViewport(1024, 768);
    const restoreMatchMedia = mockReducedMotion();

    const scrollIntoViewSpy = vi.fn();
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'r13-offscreen-motion');
    targetEl.scrollIntoView = scrollIntoViewSpy;
    // Fully off-screen: bottom < 0 → triggers scrollIntoView in measure()
    targetEl.getBoundingClientRect = () => fakeRect({
      top: -200, left: 100, width: 200, height: 50, bottom: -150, right: 300,
    });
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    const steps: CoachStep[] = [
      { selector: '[data-tour="r13-offscreen-motion"]', title: 'Offscreen', body: 'Test' },
    ];

    render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    // Immediate branch fires first (line 131, has inline: 'nearest').
    // After 280 ms the deferred measure fires (line 89, has NO inline).
    act(() => { vi.advanceTimersByTime(300); });

    // Find the call WITHOUT inline — this is the measure re-scroll at line 89.
    const measureCall = scrollIntoViewSpy.mock.calls.find(
      (call: unknown[]) => (call[0] as Record<string, unknown>)?.inline === undefined,
    );
    expect(measureCall).toBeTruthy();
    expect((measureCall![0] as Record<string, unknown>).behavior).toBe('auto');

    restoreMatchMedia();
  });

  // --- F2c: late-target / MutationObserver path (line 149) ---
  it('late-target scroll uses behavior "auto" under prefers-reduced-motion (line 149 mutation proof)', async () => {
    setViewport(1024, 768);
    const restoreMatchMedia = mockReducedMotion();

    const scrollIntoViewSpy = vi.fn();

    const steps: CoachStep[] = [
      {
        selector: '[data-tour="r13-late-motion"]',
        title: 'Late Motion',
        body: 'Test',
        waitForTargetTimeout: 5000,
      },
    ];

    render(
      <div><CoachMarks steps={steps} run={true} onClose={() => {}} /></div>,
    );

    // Should be waiting (target absent at mount)
    expect(screen.getByText('Waiting for screen to load...')).toBeInTheDocument();

    // Insert target AFTER render — only the late-target call (line 149) will use this spy.
    // The immediate branch (line 131) already ran with a different element (none),
    // so it never called scrollIntoView.
    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'r13-late-motion');
    targetEl.scrollIntoView = scrollIntoViewSpy;
    targetEl.getBoundingClientRect = () => fakeRect();
    document.body.appendChild(targetEl);
    cleanupEls.push(targetEl);

    // Wait for MutationObserver → resolveTarget → scrollIntoView
    await waitFor(() => {
      expect(scrollIntoViewSpy).toHaveBeenCalled();
    });

    // The late-target call carries inline: 'nearest' (line 149).
    const lateCall = scrollIntoViewSpy.mock.calls.find(
      (call: unknown[]) => (call[0] as Record<string, unknown>)?.inline === 'nearest',
    );
    expect(lateCall).toBeTruthy();
    expect((lateCall![0] as Record<string, unknown>).behavior).toBe('auto');

    restoreMatchMedia();
  });
});