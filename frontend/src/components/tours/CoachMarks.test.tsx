import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import CoachMarks, { tourSeen, markTourSeen, useTour, type CoachStep } from './CoachMarks';

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
      { selector: '[data-tour="nonexistent"]', title: 'Missing', body: 'No target' },
      { title: 'Next', body: 'Continue' },
    ];
    render(
      <div>
        <CoachMarks steps={steps} run={true} onClose={() => {}} />
      </div>,
    );

    await user.click(screen.getByText('Next'));
    expect(screen.getByText('Next')).toBeInTheDocument();
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

describe('useTour', () => {
  const mockStore: Record<string, string> = {};
  const originalLocalStorage = window.localStorage;
  const origMatchMedia = window.matchMedia;

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
    if (!window.matchMedia) {
      window.matchMedia = (() => ({
        matches: false,
        media: '',
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      })) as typeof window.matchMedia;
    }
  });

  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(window, 'localStorage', { value: originalLocalStorage, writable: true });
    window.matchMedia = origMatchMedia;
  });

  it('does not auto-start when tour is already seen', () => {
    markTourSeen('test_tour_ut1');
    let result: ReturnType<typeof useTour>;
    function HookTester() {
      result = useTour('test_tour_ut1');
      return null;
    }
    render(<HookTester />);
    expect(result!.run).toBe(false);
  });

  it('auto-starts after delay when tour is unseen', () => {
    vi.useFakeTimers();
    let result: ReturnType<typeof useTour>;
    function HookTester() {
      result = useTour('test_tour_ut2', true, 500);
      return null;
    }
    render(<HookTester />);
    expect(result!.run).toBe(false);

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(result!.run).toBe(true);
  });

  it('does not auto-start under prefers-reduced-motion', () => {
    vi.useFakeTimers();
    const origMatchMedia = window.matchMedia;
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    let result: ReturnType<typeof useTour>;
    function HookTester() {
      result = useTour('test_tour_ut3', true, 500);
      return null;
    }
    render(<HookTester />);

    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(result!.run).toBe(false);

    window.matchMedia = origMatchMedia;
  });

  it('allows explicit replay under prefers-reduced-motion', () => {
    const origMatchMedia = window.matchMedia;
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    let result: ReturnType<typeof useTour>;
    function HookTester() {
      result = useTour('test_tour_ut4', true, 500);
      return null;
    }
    render(<HookTester />);

    act(() => {
      result!.start();
    });
    expect(result!.run).toBe(true);

    window.matchMedia = origMatchMedia;
  });

  it('marks tour seen on close', () => {
    vi.useFakeTimers();
    let result: ReturnType<typeof useTour>;
    function HookTester() {
      result = useTour('test_tour_ut5', true, 0);
      return null;
    }
    render(<HookTester />);

    act(() => {
      vi.advanceTimersByTime(0);
    });

    act(() => {
      result!.close();
    });

    expect(tourSeen('test_tour_ut5')).toBe(true);
  });
});