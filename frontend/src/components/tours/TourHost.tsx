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

export function useTourHost() {
  const [activeTour, setActiveTour] = useState<string | null>(null);
  const [steps, setSteps] = useState<CoachStep[]>([]);
  const autoStartCheckedRef = useRef(false);

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
    setActiveTour(null);
  }, [activeTour]);

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.tour) startTour(detail.tour);
    };
    window.addEventListener('qp-tour-request', handler);
    return () => window.removeEventListener('qp-tour-request', handler);
  }, [startTour]);

  // Auto-start unseen tours once per mount; closing/skipping one does NOT chain to the next.
  useEffect(() => {
    if (autoStartCheckedRef.current) return;
    autoStartCheckedRef.current = true;
    if (activeTour) return;
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
      const timer = window.setTimeout(() => startTour(autoTour), 600);
      return () => window.clearTimeout(timer);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { activeTour, steps, closeTour, startTour };
}