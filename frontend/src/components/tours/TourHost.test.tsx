import { renderHook, act } from '@testing-library/react';
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

  it('falls back to agent tour when application is seen', () => {
    vi.useFakeTimers();
    markTourSeen(APPLICATION_TOUR_KEY);
    const { result } = renderHook(() => useTourHost());

    act(() => {
      vi.advanceTimersByTime(600);
    });

    expect(result.current.activeTour).toBe('agent');
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
