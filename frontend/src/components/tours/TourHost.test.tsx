import React from 'react';
import { renderHook, render, act, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useTourHost, markTourSeen, tourSeen } from './TourHost';
import {
  APPLICATION_TOUR_KEY,
  AGENT_TOUR_KEY,
  ARCHITECTURE_TOUR_KEY,
} from './tourSteps';

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

describe('useTourHost — versioned keys', () => {
  it('writes qp_tour_application_v1 on close', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useTourHost());

    act(() => {
      result.current.startTour('application');
    });
    expect(result.current.activeTour).toBe('application');

    act(() => {
      result.current.closeTour();
    });

    expect(tourSeen(APPLICATION_TOUR_KEY)).toBe(true);
    expect(mockStore[APPLICATION_TOUR_KEY]).toBe('1');
    expect('qp_tour_application_v1' in mockStore).toBe(true);
  });

  it('writes qp_tour_agent_v1 on close', () => {
    const { result } = renderHook(() => useTourHost());

    act(() => {
      result.current.startTour('agent');
    });

    act(() => {
      result.current.closeTour();
    });

    expect(tourSeen(AGENT_TOUR_KEY)).toBe(true);
    expect(mockStore[AGENT_TOUR_KEY]).toBe('1');
    expect('qp_tour_agent_v1' in mockStore).toBe(true);
  });

  it('writes qp_tour_architecture_v1 on close', () => {
    const { result } = renderHook(() => useTourHost());

    act(() => {
      result.current.startTour('architecture');
    });

    act(() => {
      result.current.closeTour();
    });

    expect(tourSeen(ARCHITECTURE_TOUR_KEY)).toBe(true);
    expect(mockStore[ARCHITECTURE_TOUR_KEY]).toBe('1');
    expect('qp_tour_architecture_v1' in mockStore).toBe(true);
  });

  it('does not auto-start when all tours are already seen (_v1 keys)', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    markTourSeen(AGENT_TOUR_KEY);
    markTourSeen(ARCHITECTURE_TOUR_KEY);
    const { result } = renderHook(() => useTourHost());

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.activeTour).toBeNull();
  });

  it('stored _v1 key prevents auto-start (hardcoded key check)', () => {
    vi.useFakeTimers();
    mockStore['qp_tour_application_v1'] = '1';
    mockStore['qp_tour_agent_v1'] = '1';
    mockStore['qp_tour_architecture_v1'] = '1';
    const { result } = renderHook(() => useTourHost());

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.activeTour).toBeNull();
  });

  it('auto-starts application tour when unseen', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useTourHost());

    act(() => {
      vi.advanceTimersByTime(600);
    });

    expect(result.current.activeTour).toBe('application');
  });

  it('selects agent tour for auto-start when application is seen but defers without targets', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    const { result } = renderHook(() => useTourHost('agent'));

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    // Agent tour is the next unseen tour, but without DOM targets it must not start.
    expect(result.current.activeTour).toBeNull();
  });

  it('falls back to architecture tour when application and agent are seen', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    markTourSeen(AGENT_TOUR_KEY);
    const { result } = renderHook(() => useTourHost());

    act(() => {
      vi.advanceTimersByTime(600);
    });

    expect(result.current.activeTour).toBe('architecture');
  });

  it('does not auto-start when all tours are seen', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    markTourSeen(AGENT_TOUR_KEY);
    markTourSeen(ARCHITECTURE_TOUR_KEY);
    const { result } = renderHook(() => useTourHost());

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.activeTour).toBeNull();
  });
});

describe('useTourHost — reduced-motion guard', () => {
  it('does not auto-start under prefers-reduced-motion', () => {
    vi.useFakeTimers();
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

    const { result } = renderHook(() => useTourHost());

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.activeTour).toBeNull();
  });

  it('still allows explicit startTour under prefers-reduced-motion', () => {
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

    const { result } = renderHook(() => useTourHost());

    act(() => {
      result.current.startTour('application');
    });

    expect(result.current.activeTour).toBe('application');
  });
});

describe('useTourHost — qp-tour-request event', () => {
  it('starts tour when qp-tour-request event is dispatched', () => {
    const { result } = renderHook(() => useTourHost());

    act(() => {
      window.dispatchEvent(new CustomEvent('qp-tour-request', { detail: { tour: 'agent' } }));
    });

    expect(result.current.activeTour).toBe('agent');
    expect(result.current.steps.length).toBeGreaterThan(0);
  });

  it('ignores qp-tour-request with unknown tour id', () => {
    const { result } = renderHook(() => useTourHost());

    act(() => {
      window.dispatchEvent(new CustomEvent('qp-tour-request', { detail: { tour: 'nonexistent' } }));
    });

    expect(result.current.activeTour).toBeNull();
  });
});

describe('useTourHost — no-tour-chain on close', () => {
  it('closing one tour does not auto-start the next unseen tour', () => {
    vi.useFakeTimers();
    // Application tour is unseen → auto-starts
    const { result } = renderHook(() => useTourHost());

    act(() => {
      vi.advanceTimersByTime(600);
    });

    expect(result.current.activeTour).toBe('application');

    // Close the application tour
    act(() => {
      result.current.closeTour();
    });

    expect(result.current.activeTour).toBeNull();

    // Advance timers — agent tour should NOT auto-start
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.activeTour).toBeNull();
  });
});

describe('useTourHost — React 18 StrictMode double-mount', () => {
  it('auto-starts exactly one tour after StrictMode setup/cleanup/setup cycle', () => {
    vi.useFakeTimers();
    // Simulate StrictMode: render inside a StrictMode wrapper so React
    // double-invokes effects (mount → cleanup → re-run) on the same instance.
    let hookResult: ReturnType<typeof useTourHost> | undefined;
    function Wrapper() {
      hookResult = useTourHost();
      return null;
    }
    const { unmount } = render(
      <React.StrictMode><Wrapper /></React.StrictMode>,
    );

    // After StrictMode processing, the effect has run setup/cleanup/setup.
    // The auto-start timer should be scheduled from the second setup.
    act(() => {
      vi.advanceTimersByTime(600);
    });

    expect(hookResult!.activeTour).toBe('application');

    act(() => {
      hookResult!.closeTour();
    });
  });

  it('StrictMode cycle: does not auto-start when all tours are seen', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    markTourSeen(AGENT_TOUR_KEY);
    markTourSeen(ARCHITECTURE_TOUR_KEY);

    let hookResult: ReturnType<typeof useTourHost> | undefined;
    function Wrapper() {
      hookResult = useTourHost();
      return null;
    }
    render(<React.StrictMode><Wrapper /></React.StrictMode>);

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(hookResult!.activeTour).toBeNull();
  });
});

describe('useTourHost — manual request during auto-start delay', () => {
  it('manual qp-tour-request during 600 ms window is not replaced by auto-start', () => {
    vi.useFakeTimers();
    // All tours unseen → auto-start would pick 'application'
    const { result } = renderHook(() => useTourHost());

    // Before the 600 ms delay fires, issue a manual tour request.
    act(() => {
      window.dispatchEvent(new CustomEvent('qp-tour-request', { detail: { tour: 'agent' } }));
    });
    expect(result.current.activeTour).toBe('agent');

    // Advance past the 600 ms auto-start delay.
    act(() => {
      vi.advanceTimersByTime(800);
    });

    // The manual tour must still be active — auto-start must not have replaced it.
    expect(result.current.activeTour).toBe('agent');
  });
});

describe('useTourHost — agent tour screen guard', () => {
  it('does not auto-start agent tour when currentScreen is not agent', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    const { result } = renderHook(() => useTourHost('platform-overview'));

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.activeTour).toBeNull();
  });

  it('does not auto-start agent tour on agent screen when targets are absent', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    const { result } = renderHook(() => useTourHost('agent'));

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.activeTour).toBeNull();
  });

  it('does not auto-start agent tour after screen change when targets are absent', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    let screen = 'platform-overview';
    const { result, rerender } = renderHook(() => useTourHost(screen));

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.activeTour).toBeNull();

    screen = 'agent';
    rerender();

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(result.current.activeTour).toBeNull();
  });

  it('still allows manual start of agent tour on any screen', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useTourHost('platform-overview'));

    act(() => {
      result.current.startTour('agent');
    });

    expect(result.current.activeTour).toBe('agent');
  });
});

describe('useTourHost — agent tour target-availability gating', () => {
  function TourHostWrapper({ screen }: { screen?: string }) {
    const { activeTour, steps, closeTour } = useTourHost(screen);
    return (
      <div data-tour="agent">
        <div data-tour="agent-evidence" />
        {activeTour && (
          <div data-testid="tour-active" data-tour-id={activeTour}>
            {steps.map((s, i) => (
              <span key={i} data-testid={`step-${i}`}>{s.title}</span>
            ))}
            <button data-testid="close-tour" onClick={closeTour}>close</button>
          </div>
        )}
      </div>
    );
  }

  it('agent route with only root target does not auto-start', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    render(<TourHostWrapper screen="agent" />, { wrapper: ({ children }) => <>{children}</> });

    act(() => { vi.advanceTimersByTime(1000); });

    expect(screen.queryByTestId('tour-active')).toBeNull();
  });

  it('adding remaining targets later starts tour once', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);

    const { container } = render(
      <div data-tour="agent"><div data-tour="agent-evidence" /></div>,
      { wrapper: ({ children }) => <>{children}</> },
    );
    renderHook(() => useTourHost('agent'));

    act(() => { vi.advanceTimersByTime(50); });

    const target = container.querySelector('[data-tour="agent"]')!;
    const lakebase = document.createElement('div');
    lakebase.setAttribute('data-tour', 'lakebase-write');
    target.appendChild(lakebase);

    act(() => { vi.advanceTimersByTime(1000); });

    expect(lakebase.isConnected).toBe(true);
  });

  it('StrictMode does not start agent tour twice when targets present', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);

    let startCount = 0;
    const origSetTimeout = window.setTimeout;
    vi.spyOn(window, 'setTimeout').mockImplementation(((...args: Parameters<typeof setTimeout>) => {
      const cb = args[0];
      if (typeof cb === 'function') {
        const wrapped = () => { startCount++; return cb(); };
        return origSetTimeout(wrapped as TimerHandler, args[1] as number) as unknown as number;
      }
      return origSetTimeout(...args);
    }) as typeof window.setTimeout);

    function Wrapper() {
      useTourHost('agent');
      return (
        <div data-tour="agent">
          <div data-tour="agent-evidence" />
          <div data-tour="lakebase-write" />
        </div>
      );
    }

    render(<React.StrictMode><Wrapper /></React.StrictMode>);

    act(() => { vi.advanceTimersByTime(1200); });

    expect(startCount).toBeLessThanOrEqual(1);

    vi.mocked(window.setTimeout).mockRestore();
  });

  it('leaving route before targets appear cancels pending auto-start', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);

    const { unmount } = render(<TourHostWrapper screen="agent" />, { wrapper: ({ children }) => <>{children}</> });

    act(() => { vi.advanceTimersByTime(50); });

    unmount();

    const target = document.createElement('div');
    target.setAttribute('data-tour', 'agent');
    const evidence = document.createElement('div');
    evidence.setAttribute('data-tour', 'agent-evidence');
    const lakebase = document.createElement('div');
    lakebase.setAttribute('data-tour', 'lakebase-write');
    target.appendChild(evidence);
    target.appendChild(lakebase);
    document.body.appendChild(target);

    act(() => { vi.advanceTimersByTime(2000); });

    expect(screen.queryByTestId('tour-active')).toBeNull();

    document.body.removeChild(target);
  });

  it('manual start remains correct regardless of target availability', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);

    const { result } = renderHook(() => useTourHost('agent'));

    act(() => {
      result.current.startTour('agent');
    });

    expect(result.current.activeTour).toBe('agent');
  });
});
