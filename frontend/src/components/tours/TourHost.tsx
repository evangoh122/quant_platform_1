import { useCallback, useEffect, useRef, useState } from 'react';
import CoachMarks, { tourSeen, markTourSeen, type CoachStep } from './CoachMarks';
import {
  APPLICATION_TOUR_KEY,
  AGENT_TOUR_KEY,
  ARCHITECTURE_TOUR_KEY,
  APPLICATION_TOUR,
  AGENT_TOUR,
  ARCHITECTURE_TOUR,
} from './tourSteps';

export { CoachMarks, tourSeen, markTourSeen };
export type { CoachStep };

const TOUR_MAP: Record<string, { key: string; steps: CoachStep[] }> = {
  application: { key: APPLICATION_TOUR_KEY, steps: APPLICATION_TOUR },
  agent: { key: AGENT_TOUR_KEY, steps: AGENT_TOUR },
  architecture: { key: ARCHITECTURE_TOUR_KEY, steps: ARCHITECTURE_TOUR },
};

function allTourTargetsPresent(tourSteps: CoachStep[]): boolean {
  for (const step of tourSteps) {
    if (step.selector && !document.querySelector(step.selector)) return false;
  }
  return true;
}

export function useTourHost(currentScreen?: string) {
  const [activeTour, setActiveTour] = useState<string | null>(null);
  const [steps, setSteps] = useState<CoachStep[]>([]);
  const manualStartRef = useRef(false);
  const screenRef = useRef(currentScreen);
  screenRef.current = currentScreen;
  const autoStartDoneRef = useRef(false);
  const mainTimerRef = useRef<number | null>(null);

  const startTour = useCallback((tourId: string) => {
    const tour = TOUR_MAP[tourId];
    if (!tour) return;
    setSteps(tour.steps);
    setActiveTour(tourId);
  }, []);

  const closeTour = useCallback(() => {
    if (activeTour) {
      const tour = TOUR_MAP[activeTour];
      if (tour) markTourSeen(tour.key);
    }
    manualStartRef.current = false;
    setActiveTour(null);
  }, [activeTour]);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.tour) {
        manualStartRef.current = true;
        startTour(detail.tour);
      }
    };
    window.addEventListener('qp-tour-request', handler);
    return () => window.removeEventListener('qp-tour-request', handler);
  }, [startTour]);

  // Auto-start unseen tours once per mount; closing/skipping one does NOT chain to the next.
  // Re-evaluates when currentScreen changes so the agent tour can start once the
  // user navigates to the Research Agent screen where its targets are present.
  useEffect(() => {
    if (activeTour || autoStartDoneRef.current) return;
    const prefersReducedMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)',
    ).matches;
    if (prefersReducedMotion) return;

    const autoTour =
      !tourSeen(APPLICATION_TOUR_KEY)
        ? 'application'
        : !tourSeen(AGENT_TOUR_KEY)
          ? 'agent'
          : !tourSeen(ARCHITECTURE_TOUR_KEY)
            ? 'architecture'
            : null;

    if (autoTour) {
      // Do not auto-start the agent tour unless the user is on the agent screen,
      // where step targets (agent, lakebase-write, agent-evidence) are present.
      // When currentScreen is not provided, skip the guard (standalone hook usage).
      if (autoTour === 'agent' && currentScreen !== undefined && currentScreen !== 'agent') {
        return;
      }
      autoStartDoneRef.current = true;

      const scheduleAutoStart = () => {
        mainTimerRef.current = window.setTimeout(() => {
          if (manualStartRef.current) return;
          const tour = TOUR_MAP[autoTour];
          if (tour && tourSeen(tour.key)) return;
          startTour(autoTour);
        }, 600);
      };

      // For the agent tour, verify all step targets exist in the DOM before
      // scheduling. Targets like [data-tour="lakebase-write"] and
      // [data-tour="agent-evidence"] may render after the route mounts.
      if (autoTour === 'agent' && !allTourTargetsPresent(AGENT_TOUR)) {
        const agentObserver = new MutationObserver(() => {
          if (allTourTargetsPresent(AGENT_TOUR)) {
            agentObserver.disconnect();
            scheduleAutoStart();
          }
        });
        agentObserver.observe(document.body, { childList: true, subtree: true });
        const observerFallback = window.setTimeout(() => {
          agentObserver.disconnect();
        }, 10000);
        return () => {
          window.clearTimeout(observerFallback);
          agentObserver.disconnect();
          if (mainTimerRef.current != null) window.clearTimeout(mainTimerRef.current);
          autoStartDoneRef.current = false;
        };
      }

      scheduleAutoStart();
      return () => {
        if (mainTimerRef.current != null) window.clearTimeout(mainTimerRef.current);
        autoStartDoneRef.current = false;
      };
    }
  }, [currentScreen]); // eslint-disable-line react-hooks/exhaustive-deps

  return { activeTour, steps, closeTour, startTour };
}