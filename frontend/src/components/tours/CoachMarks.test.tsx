import { useState } from 'react';
import { render, screen, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import CoachMarks, { tourSeen, markTourSeen, type CoachStep } from './CoachMarks';

const STEPS: CoachStep[] = [
  { title: 'Step 1', body: 'First step' },
  { selector: '[data-tour="target"]', title: 'Step 2', body: 'Second step with target' },
  { title: 'Step 3', body: 'Third step' },
];

function Target() {
  return <div data-tour="target">Target element</div>;
}

function TestComponent({ steps = STEPS, run = true }: { steps?: CoachStep[]; run?: boolean }) {
  return (
    <div>
      <Target />
      <CoachMarks steps={steps} run={run} onClose={() => {}} />
    </div>
  );
}

describe('CoachMarks', () => {
  it('renders nothing when run is false', () => {
    render(<TestComponent run={false} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders the first step when run is true', () => {
    render(<TestComponent />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
    expect(screen.getByText('Step 1')).toBeInTheDocument();
    expect(screen.getByText('First step')).toBeInTheDocument();
  });

  it('navigates to the next step on Next click', async () => {
    const user = userEvent.setup();
    render(<TestComponent />);

    await user.click(screen.getByText('Next'));
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument();
    expect(screen.getByText('Step 2')).toBeInTheDocument();
  });

  it('navigates back on Back click', async () => {
    const user = userEvent.setup();
    render(<TestComponent />);

    await user.click(screen.getByText('Next'));
    await user.click(screen.getByText('Back'));
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
  });

  it('does not show Back on the first step', () => {
    render(<TestComponent />);
    expect(screen.queryByText('Back')).not.toBeInTheDocument();
  });

  it('shows Done on the last step', async () => {
    const user = userEvent.setup();
    render(<TestComponent />);

    await user.click(screen.getByText('Next'));
    await user.click(screen.getByText('Next'));
    expect(screen.getByText('Done')).toBeInTheDocument();
  });

  it('calls onClose when Done is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <div>
        <Target />
        <CoachMarks steps={STEPS} run={true} onClose={onClose} />
      </div>,
    );

    await user.click(screen.getByText('Next'));
    await user.click(screen.getByText('Next'));
    await user.click(screen.getByText('Done'));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose when Skip tour is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <div>
        <Target />
        <CoachMarks steps={STEPS} run={true} onClose={onClose} />
      </div>,
    );

    await user.click(screen.getByText('Skip tour'));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose on Escape key', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <div>
        <Target />
        <CoachMarks steps={STEPS} run={true} onClose={onClose} />
      </div>,
    );

    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('navigates with ArrowRight and ArrowLeft', async () => {
    const user = userEvent.setup();
    render(<TestComponent />);

    await user.keyboard('{ArrowRight}');
    expect(screen.getByText('Step 2 of 3')).toBeInTheDocument();

    await user.keyboard('{ArrowLeft}');
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
  });

  it('ArrowLeft does not wrap to last step', async () => {
    const user = userEvent.setup();
    render(<TestComponent />);

    await user.keyboard('{ArrowLeft}');
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();
  });

  it('renders as dialog with aria-modal', () => {
    render(<TestComponent />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-label', 'Guided tour');
  });

  it('renders a centered step when selector is missing', () => {
    const steps: CoachStep[] = [
      { selector: '[data-tour="nonexistent"]', title: 'Missing', body: 'No target' },
    ];
    render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );
    expect(screen.getByText('Missing')).toBeInTheDocument();
    expect(screen.getByText('No target')).toBeInTheDocument();
  });

  it('continues to next step when current selector is missing', async () => {
    const user = userEvent.setup();
    const steps: CoachStep[] = [
      { selector: '[data-tour="nonexistent"]', title: 'Missing Step', body: 'No target' },
      { title: 'Continue Step', body: 'Continue' },
    ];
    render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    expect(screen.getByText('Missing Step')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Continue Step')).toBeInTheDocument();
  });

  it('closes on Escape and restores focus to the opener', () => {
    vi.useFakeTimers();
    const opener = document.createElement('button');
    opener.textContent = 'Opener';
    document.body.appendChild(opener);
    opener.focus();

    function FocusTest() {
      const [run, setRun] = useState(true);
      return (
        <div>
          <Target />
          <CoachMarks steps={STEPS} run={run} onClose={() => setRun(false)} />
        </div>
      );
    }

    render(<FocusTest />);

    fireEvent.keyDown(window, { key: 'Escape' });

    act(() => {
      vi.advanceTimersByTime(0);
    });

    expect(document.activeElement).toBe(opener);

    vi.useRealTimers();
    document.body.removeChild(opener);
  });

  it('closes on Done and restores focus to the opener', () => {
    vi.useFakeTimers();
    const opener = document.createElement('button');
    opener.textContent = 'Opener';
    document.body.appendChild(opener);
    opener.focus();

    function FocusTest() {
      const [run, setRun] = useState(true);
      return (
        <div>
          <Target />
          <CoachMarks steps={STEPS} run={run} onClose={() => setRun(false)} />
        </div>
      );
    }

    render(<FocusTest />);

    const nextButton = screen.getByRole('button', { name: 'Next' });
    fireEvent.click(nextButton);
    fireEvent.click(nextButton);
    const doneButton = screen.getByRole('button', { name: 'Done' });
    fireEvent.click(doneButton);

    act(() => {
      vi.advanceTimersByTime(0);
    });

    expect(document.activeElement).toBe(opener);

    vi.useRealTimers();
    document.body.removeChild(opener);
  });

  it('repositions the spotlight after resize', () => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 768, writable: true });
    const initialRect = { top: 100, left: 100, width: 200, height: 50, bottom: 150, right: 300, x: 100, y: 100, toJSON: () => {} } as DOMRect;
    const updatedRect = { top: 300, left: 400, width: 200, height: 50, bottom: 350, right: 600, x: 400, y: 300, toJSON: () => {} } as DOMRect;
    let currentRect = initialRect;

    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'spotlight-target');
    targetEl.getBoundingClientRect = () => currentRect;
    document.body.appendChild(targetEl);

    const steps: CoachStep[] = [
      { selector: '[data-tour="spotlight-target"]', title: 'Spotlight', body: 'Test' },
    ];

    const { container } = render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    const PAD = 8;
    const dialog = container.querySelector('[role="dialog"]')!;

    act(() => { vi.advanceTimersByTime(280); });

    const spotlight = dialog.children[0] as HTMLElement;
    expect(spotlight).toBeTruthy();
    expect(spotlight.style.left).toBe(`${initialRect.left - PAD}px`);

    currentRect = updatedRect;
    act(() => { fireEvent.resize(window); vi.advanceTimersByTime(0); });

    const spotlightAfter = dialog.children[0] as HTMLElement;
    expect(spotlightAfter.style.left).toBe(`${updatedRect.left - PAD}px`);
    expect(spotlightAfter.style.top).toBe(`${updatedRect.top - PAD}px`);

    vi.useRealTimers();
    document.body.removeChild(targetEl);
  });

  it('repositions the spotlight after scroll', () => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 768, writable: true });
    const initialRect = { top: 100, left: 100, width: 200, height: 50, bottom: 150, right: 300, x: 100, y: 100, toJSON: () => {} } as DOMRect;
    const updatedRect = { top: 50, left: 50, width: 200, height: 50, bottom: 100, right: 250, x: 50, y: 50, toJSON: () => {} } as DOMRect;
    let currentRect = initialRect;

    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'scroll-target');
    targetEl.getBoundingClientRect = () => currentRect;
    document.body.appendChild(targetEl);

    const steps: CoachStep[] = [
      { selector: '[data-tour="scroll-target"]', title: 'Scroll', body: 'Test' },
    ];

    const { container } = render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    const PAD = 8;
    const dialog = container.querySelector('[role="dialog"]')!;

    act(() => { vi.advanceTimersByTime(280); });

    const spotlight = dialog.children[0] as HTMLElement;
    expect(spotlight).toBeTruthy();
    expect(spotlight.style.left).toBe(`${initialRect.left - PAD}px`);

    currentRect = updatedRect;
    act(() => { fireEvent.scroll(window); vi.advanceTimersByTime(0); });

    const spotlightAfter = dialog.children[0] as HTMLElement;
    expect(spotlightAfter.style.left).toBe(`${updatedRect.left - PAD}px`);
    expect(spotlightAfter.style.top).toBe(`${updatedRect.top - PAD}px`);

    vi.useRealTimers();
    document.body.removeChild(targetEl);
  });

  it('traps focus inside the dialog when focus moves outside', () => {
    render(<TestComponent />);

    const dialog = screen.getByRole('dialog');
    const card = dialog.querySelector('[tabindex="-1"]') as HTMLElement;
    expect(card).toBeTruthy();

    const outside = document.createElement('button');
    outside.textContent = 'Outside';
    document.body.appendChild(outside);

    outside.focus();

    expect(document.activeElement).toBe(card);

    document.body.removeChild(outside);
  });

  it('clamps spotlight left to 0 when target is at x=-20', () => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 768, writable: true });
    const negativeRect = { top: 100, left: -20, width: 200, height: 50, bottom: 150, right: 180, x: -20, y: 100, toJSON: () => {} } as DOMRect;

    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'negative-target');
    targetEl.getBoundingClientRect = () => negativeRect;
    document.body.appendChild(targetEl);

    const steps: CoachStep[] = [
      { selector: '[data-tour="negative-target"]', title: 'Neg', body: 'Test' },
    ];

    const { container } = render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    const PAD = 8;
    const dialog = container.querySelector('[role="dialog"]')!;
    act(() => { vi.advanceTimersByTime(280); });

    const spotlight = dialog.children[0] as HTMLElement;
    expect(spotlight).toBeTruthy();
    expect(parseInt(spotlight.style.left, 10)).toBeGreaterThanOrEqual(0);
    expect(parseInt(spotlight.style.left, 10) + parseInt(spotlight.style.width, 10)).toBeLessThanOrEqual(1024);

    vi.useRealTimers();
    document.body.removeChild(targetEl);
  });

  it('clamps spotlight to viewport when target is wider than viewport (1024px)', () => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 768, writable: true });
    const wideRect = { top: 100, left: 0, width: 1200, height: 50, bottom: 150, right: 1200, x: 0, y: 100, toJSON: () => {} } as DOMRect;

    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'wide-target');
    targetEl.getBoundingClientRect = () => wideRect;
    document.body.appendChild(targetEl);

    const steps: CoachStep[] = [
      { selector: '[data-tour="wide-target"]', title: 'Wide', body: 'Test' },
    ];

    const { container } = render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    const dialog = container.querySelector('[role="dialog"]')!;
    act(() => { vi.advanceTimersByTime(280); });

    const spotlight = dialog.children[0] as HTMLElement;
    expect(spotlight).toBeTruthy();
    expect(parseInt(spotlight.style.left, 10)).toBeGreaterThanOrEqual(0);
    expect(parseInt(spotlight.style.left, 10) + parseInt(spotlight.style.width, 10)).toBeLessThanOrEqual(1024);

    vi.useRealTimers();
    document.body.removeChild(targetEl);
  });

  it('renders overlay instead of spotlight at 360px mobile viewport', () => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'innerWidth', { value: 360, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 768, writable: true });
    const wideRect = { top: 100, left: 0, width: 1200, height: 50, bottom: 150, right: 1200, x: 0, y: 100, toJSON: () => {} } as DOMRect;

    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'wide-target-360');
    targetEl.getBoundingClientRect = () => wideRect;
    document.body.appendChild(targetEl);

    const steps: CoachStep[] = [
      { selector: '[data-tour="wide-target-360"]', title: 'Wide', body: 'Test' },
    ];

    const { container } = render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    const dialog = container.querySelector('[role="dialog"]')!;
    act(() => { vi.advanceTimersByTime(280); });

    const overlay = dialog.children[0] as HTMLElement;
    expect(overlay).toBeTruthy();
    expect(overlay.className).toContain('bg-black');

    vi.useRealTimers();
    document.body.removeChild(targetEl);
  });

  it('clamps spotlight when target is entirely off-screen to the right', () => {
    vi.useFakeTimers();
    Object.defineProperty(window, 'innerWidth', { value: 1024, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 768, writable: true });
    const offRight = { top: 100, left: 1200, width: 100, height: 50, bottom: 150, right: 1300, x: 1200, y: 100, toJSON: () => {} } as DOMRect;

    const targetEl = document.createElement('div');
    targetEl.setAttribute('data-tour', 'offright-target');
    targetEl.getBoundingClientRect = () => offRight;
    document.body.appendChild(targetEl);

    const steps: CoachStep[] = [
      { selector: '[data-tour="offright-target"]', title: 'OffRight', body: 'Test' },
    ];

    const { container } = render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    const dialog = container.querySelector('[role="dialog"]')!;
    act(() => { vi.advanceTimersByTime(280); });

    const spotlight = dialog.children[0] as HTMLElement;
    expect(spotlight).toBeTruthy();
    const w = parseInt(spotlight.style.width, 10);
    const l = parseInt(spotlight.style.left, 10);
    expect(w).toBeGreaterThanOrEqual(0);
    expect(l).toBeGreaterThanOrEqual(0);
    expect(l + w).toBeLessThanOrEqual(1024);

    vi.useRealTimers();
    document.body.removeChild(targetEl);
  });
  describe('Tab wrap cycling', () => {
    it('cycles Tab from last focusable to first inside the coach card', async () => {
      const user = userEvent.setup();
      render(<TestComponent />);

      const dialog = screen.getByRole('dialog');
      const buttons = dialog.querySelectorAll('button');
      const lastButton = buttons[buttons.length - 1];

      // Focus the last button
      lastButton.focus();

      // Tab should wrap to the first focusable element
      await user.keyboard('{Tab}');
      expect(document.activeElement).toBe(buttons[0]);
    });

    it('cycles Shift+Tab from first to last inside the coach card', async () => {
      const user = userEvent.setup();
      render(<TestComponent />);

      const dialog = screen.getByRole('dialog');
      const buttons = dialog.querySelectorAll('button');
      const firstButton = buttons[0];

      firstButton.focus();

      await user.keyboard('{Shift>}{Tab}{/Shift}');
      expect(document.activeElement).toBe(buttons[buttons.length - 1]);
    });

    it('retains focus on the card when there are no focusable children', () => {
      const noButtonSteps: CoachStep[] = [
        { title: 'No buttons', body: 'Just text' },
      ];
      // Use a step with no interactive elements; the card itself is focusable
      render(
        <div>
          <CoachMarks steps={noButtonSteps} run={true} onClose={() => {}} />
        </div>,
      );

      const dialog = screen.getByRole('dialog');
      const card = dialog.querySelector('[tabindex="-1"]') as HTMLElement;
      expect(card).toBeTruthy();
      expect(document.activeElement).toBe(card);
    });
  });

  describe('StrictMode once-only guard', () => {
    const TOUR_KEY = 'test_strictmode_v1';
    const mockStore: Record<string, string> = {};
    const originalLocalStorage = window.localStorage;

    beforeEach(() => {
      Object.keys(mockStore).forEach((k) => delete mockStore[k]);
      Object.defineProperty(window, 'localStorage', {
        value: {
          getItem: (k: string) => (k in mockStore ? mockStore[k] : null),
          setItem: (k: string, v: string) => { mockStore[k] = v; },
          removeItem: (k: string) => { delete mockStore[k]; },
          clear: () => { Object.keys(mockStore).forEach((k) => delete mockStore[k]); },
        },
        writable: true,
      });
    });

    afterEach(() => {
      Object.defineProperty(window, 'localStorage', { value: originalLocalStorage, writable: true });
    });

    function StrictModeHarness({ onDone }: { onDone: () => void }) {
      const [run, setRun] = useState(true);
      return (
        <React.StrictMode>
          <div>
            <Target />
            <CoachMarks
              steps={STEPS}
              run={run}
              onClose={() => {
                setRun(false);
                markTourSeen(TOUR_KEY);
                onDone();
              }}
            />
          </div>
        </React.StrictMode>
      );
    }

    it('Done: onClose once, markTourSeen once, no "Cannot update a component" warning', async () => {
      const onDone = vi.fn();
      const setItemSpy = vi.spyOn(window.localStorage, 'setItem');
      const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(<StrictModeHarness onDone={onDone} />);

      const nextBtn = screen.getByRole('button', { name: 'Next' });
      fireEvent.click(nextBtn);
      fireEvent.click(nextBtn);
      const doneBtn = screen.getByRole('button', { name: 'Done' });
      fireEvent.click(doneBtn);

      expect(onDone).toHaveBeenCalledTimes(1);
      expect(setItemSpy).toHaveBeenCalledTimes(1);
      expect(setItemSpy).toHaveBeenCalledWith(TOUR_KEY, '1');

      const cannotUpdateCalls = errSpy.mock.calls.filter(
        (args) =>
          typeof args[0] === 'string' &&
          args[0].includes('Cannot update a component'),
      );
      expect(cannotUpdateCalls).toHaveLength(0);

      errSpy.mockRestore();
      setItemSpy.mockRestore();
    });

    it('Escape: onClose once, markTourSeen once, no "Cannot update a component" warning', async () => {
      const onDone = vi.fn();
      const setItemSpy = vi.spyOn(window.localStorage, 'setItem');
      const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      render(<StrictModeHarness onDone={onDone} />);

      fireEvent.keyDown(window, { key: 'Escape' });

      expect(onDone).toHaveBeenCalledTimes(1);
      expect(setItemSpy).toHaveBeenCalledTimes(1);
      expect(setItemSpy).toHaveBeenCalledWith(TOUR_KEY, '1');

      const cannotUpdateCalls = errSpy.mock.calls.filter(
        (args) =>
          typeof args[0] === 'string' &&
          args[0].includes('Cannot update a component'),
      );
      expect(cannotUpdateCalls).toHaveLength(0);

      errSpy.mockRestore();
      setItemSpy.mockRestore();
    });
  });
});

describe('tourSeen / markTourSeen', () => {
  const mockStore: Record<string, string> = {};
  const originalLocalStorage = window.localStorage;

  beforeEach(() => {
    Object.keys(mockStore).forEach((k) => delete mockStore[k]);
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: (k: string) => (k in mockStore ? mockStore[k] : null),
        setItem: (k: string, v: string) => { mockStore[k] = v; },
        removeItem: (k: string) => { delete mockStore[k]; },
        clear: () => { Object.keys(mockStore).forEach((k) => delete mockStore[k]); },
      },
      writable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'localStorage', { value: originalLocalStorage, writable: true });
  });

  it('returns false for unseen tour', () => {
    expect(tourSeen('test_key_ts1')).toBe(false);
  });

  it('returns true after marking seen', () => {
    markTourSeen('test_key_ts2');
    expect(tourSeen('test_key_ts2')).toBe(true);
  });

  it('handles localStorage errors gracefully', () => {
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: () => { throw new Error('blocked'); },
        setItem: () => { throw new Error('blocked'); },
      },
      writable: true,
    });
    expect(tourSeen('test_key_ts3')).toBe(true);
  });
});