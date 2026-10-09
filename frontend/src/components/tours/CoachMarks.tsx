import {
  type CSSProperties,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';

export interface CoachStep {
  selector?: string;
  title: string;
  body: string;
  placement?: 'top' | 'bottom' | 'auto';
  /** Screen ID to navigate to before showing this step (for cross-screen tours) */
  navigateTo?: string;
  /** Timeout in ms to wait for target to appear (default: 3000) */
  waitForTargetTimeout?: number;
}

interface CoachMarksProps {
  steps: CoachStep[];
  run: boolean;
  onClose: () => void;
  /** Called when a step requests navigation to a different screen */
  onNavigate?: (screenId: string) => void;
  /** Current screen ID, used to restore the screen on tour close */
  currentScreen?: string;
}

const PAD = 8;
const CARD_W = 320;

export default function CoachMarks({ steps, run, onClose, onNavigate, currentScreen }: CoachMarksProps) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [waitingForTarget, setWaitingForTarget] = useState(false);
  const [targetTimedOut, setTargetTimedOut] = useState(false);
  const [screenAnnouncement, setScreenAnnouncement] = useState('');
  const cardRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const observerRef = useRef<MutationObserver | null>(null);
  const initialScreenRef = useRef<string | undefined>(undefined);

  const step = steps[index];

  const measure = useCallback(() => {
    if (!step?.selector) {
      setRect(null);
      return;
    }
    const el = document.querySelector(step.selector) as HTMLElement | null;
    if (!el) {
      setRect(null);
      return;
    }
    const r = el.getBoundingClientRect();
    const w = window.innerWidth;
    const h = window.innerHeight;
    const fullyOffScreen = r.bottom < 0 || r.top > h || r.right < 0 || r.left > w;
    if (fullyOffScreen) {
      const motion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      el.scrollIntoView({ block: 'center', behavior: motion ? 'auto' : 'smooth' });
    }
    setRect(el.getBoundingClientRect());
  }, [step]);

  useEffect(() => {
    if (run) {
      openerRef.current = document.activeElement as HTMLElement;
      initialScreenRef.current = currentScreen;
      setIndex(0);
      setTargetTimedOut(false);
    }
  }, [run, currentScreen]);

  // Handle navigation and target waiting for cross-screen steps
  useLayoutEffect(() => {
    if (!run || !step) return;
    setTargetTimedOut(false);

    // If step requires navigation, trigger it first
    if (step.navigateTo && onNavigate) {
      onNavigate(step.navigateTo);
      setScreenAnnouncement(`Navigated to ${step.navigateTo} screen`);
    }

    const timeout = step.waitForTargetTimeout ?? 3000;

    // If step has a selector, check if target exists
    if (step.selector) {
      const el = document.querySelector(step.selector) as HTMLElement | null;

      if (el) {
        // Target exists immediately
        setWaitingForTarget(false);
        const motion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        el.scrollIntoView({ behavior: motion ? 'auto' : 'smooth', block: 'center', inline: 'nearest' });
        const t = window.setTimeout(measure, 280);
        return () => window.clearTimeout(t);
      } else {
        // Target not found - wait with bounded observer/timeout
        setWaitingForTarget(true);
        setTargetTimedOut(false);
        let resolved = false;

        const resolveTarget = () => {
          if (resolved) return;
          resolved = true;
          setWaitingForTarget(false);
          const foundEl = document.querySelector(step.selector!) as HTMLElement | null;
          if (foundEl) {
            setTargetTimedOut(false);
            const motion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            foundEl.scrollIntoView({ behavior: motion ? 'auto' : 'smooth', block: 'center', inline: 'nearest' });
            setTimeout(measure, 280);
          } else {
            setTargetTimedOut(true);
          }
        };

        // Set up MutationObserver to watch for target
        const observer = new MutationObserver(() => {
          if (document.querySelector(step.selector!)) {
            observer.disconnect();
            resolveTarget();
          }
        });
        observerRef.current = observer;
        observer.observe(document.body, { childList: true, subtree: true });

        // Bounded timeout - if target doesn't appear, show skip/defer state
        const timeoutId = window.setTimeout(() => {
          observer.disconnect();
          resolveTarget();
        }, timeout);

        return () => {
          observer.disconnect();
          window.clearTimeout(timeoutId);
        };
      }
    } else {
      // No selector - centered card (introductory step)
      setWaitingForTarget(false);
      setRect(null);
    }
  }, [run, step, measure, onNavigate]);

  useEffect(() => {
    if (!run) return;
    const onChange = () => measure();
    window.addEventListener('resize', onChange);
    window.addEventListener('scroll', onChange, true);
    return () => {
      window.removeEventListener('resize', onChange);
      window.removeEventListener('scroll', onChange, true);
    };
  }, [run, measure]);

  useEffect(() => {
    if (!run || !cardRef.current) return;
    cardRef.current.focus();
  }, [run, index]);

  // Tab wrap: cycle from last focusable to first and Shift+Tab from first to last
  useEffect(() => {
    if (!run) return;
    const card = cardRef.current;
    if (!card) return;

    function getFocusable(): HTMLElement[] {
      return Array.from(
        card!.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute('disabled') && el.tabIndex !== -1);
    }

    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;
      const focusable = getFocusable();
      if (focusable.length === 0) {
        e.preventDefault();
        card!.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first || document.activeElement === card) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    card.addEventListener('keydown', onKeyDown);
    return () => card.removeEventListener('keydown', onKeyDown);
  }, [run, index]);

  const handleClose = useCallback(() => {
    if (initialScreenRef.current !== undefined && onNavigate) {
      onNavigate(initialScreenRef.current);
    }
    onClose();
    setTimeout(() => openerRef.current?.focus(), 0);
  }, [onClose, onNavigate]);

  const next = useCallback(() => {
    if (index >= steps.length - 1) {
      handleClose();
      return;
    }
    setIndex((i) => i + 1);
  }, [index, steps.length, handleClose]);

  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  useEffect(() => {
    if (!run) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
      else if (e.key === 'ArrowRight') next();
      else if (e.key === 'ArrowLeft') back();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [run, next, back, handleClose]);

  useEffect(() => {
    if (!run) return;
    const card = cardRef.current;
    if (!card) return;
    const onFocus = (e: FocusEvent) => {
      if (!card.contains(e.target as Node)) {
        e.stopPropagation();
        card.focus();
      }
    };
    document.addEventListener('focusin', onFocus);
    return () => document.removeEventListener('focusin', onFocus);
  }, [run]);

  if (!run || !step) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const isMobile = vw < 640;

  // Show waiting state if we're waiting for a target
  if (waitingForTarget || targetTimedOut) {
    return (
      <div className="fixed inset-0 z-[200]" role="dialog" aria-modal="true" aria-label="Guided tour">
        <div className="absolute inset-0 bg-black/58" />
        <div
          ref={cardRef}
          tabIndex={-1}
          className="absolute left-1/2 bottom-5 -translate-x-1/2 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-5 shadow-2xl focus:outline-none"
          style={{ width: Math.min(CARD_W, vw - 24) }}
        >
          <div className="flex items-start justify-between gap-3 mb-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Step {index + 1} of {steps.length}
            </span>
            <button
              onClick={handleClose}
              aria-label="Skip tour"
              className="p-1 -m-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] bg-transparent border-0 cursor-pointer"
            >
              &times;
            </button>
          </div>
          <h3 className="text-[15px] font-semibold text-[var(--text-primary)] mb-1.5 tracking-tight">
            {step.title}
          </h3>
          <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed m-0">
            {step.body}
          </p>
          {targetTimedOut ? (
            <p className="mt-2 text-[12px] text-[var(--warning)] italic" role="status" aria-live="polite">
              This step's target could not be shown.
            </p>
          ) : (
            <p className="mt-2 text-[12px] text-[var(--text-muted)] italic">
              Waiting for screen to load...
            </p>
          )}
          <div className="flex items-center justify-end gap-2 mt-4">
            <button
              onClick={() => {
                if (index >= steps.length - 1) {
                  handleClose();
                } else {
                  setIndex((i) => i + 1);
                }
              }}
              className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] bg-transparent border-0 p-0 cursor-pointer"
            >
              {targetTimedOut ? 'Skip step' : 'Skip step'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  let cardStyle: CSSProperties;
  if (!rect || isMobile) {
    cardStyle = {
      left: Math.max(12, (vw - Math.min(CARD_W, vw - 24)) / 2),
      bottom: 20,
      width: Math.min(CARD_W, vw - 24),
    };
  } else {
    const effectivePlacement = step?.placement ?? 'auto';
    const below = rect.bottom + 12;
    const above = vh - rect.top + 12;
    let wantAbove: boolean;
    if (effectivePlacement === 'top') {
      wantAbove = true;
    } else if (effectivePlacement === 'bottom') {
      wantAbove = false;
    } else {
      wantAbove = below + 180 > vh && rect.top > 200;
    }
    const top = wantAbove ? undefined : below;
    const bottom = wantAbove ? above : undefined;
    let left = rect.left + rect.width / 2 - CARD_W / 2;
    left = Math.min(Math.max(12, left), vw - CARD_W - 12);
    cardStyle = { left, top, bottom, width: CARD_W };
  }

  return (
    <div className="fixed inset-0 z-[200]" role="dialog" aria-modal="true" aria-label="Guided tour">
      {rect && !isMobile ? (() => {
        const raw = {
          left: rect.left - PAD,
          top: rect.top - PAD,
          width: rect.width + PAD * 2,
          height: rect.height + PAD * 2,
        };
        const clampedLeft = Math.max(0, Math.min(raw.left, vw));
        const clampedRight = Math.max(0, Math.min(raw.left + raw.width, vw));
        const clampedTop = Math.max(0, Math.min(raw.top, vh));
        const clampedBottom = Math.max(0, Math.min(raw.top + raw.height, vh));
        const clamped = {
          left: clampedLeft,
          top: clampedTop,
          width: Math.max(0, clampedRight - clampedLeft),
          height: Math.max(0, clampedBottom - clampedTop),
        };
        return (
        <div
          className="absolute rounded-xl pointer-events-none transition-all duration-200"
          style={{
            left: clamped.left,
            top: clamped.top,
            width: clamped.width,
            height: clamped.height,
            boxShadow: '0 0 0 9999px rgba(0,0,0,0.58)',
            border: '2px solid var(--accent, #6366f1)',
          }}
        />
      ) })() : (
        <div className="absolute inset-0 bg-black/58" />
      )}

      <div className="absolute inset-0" onClick={(e) => e.stopPropagation()} />

      <div
        ref={cardRef}
        tabIndex={-1}
        className="absolute rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 sm:p-5 shadow-2xl focus:outline-none"
        style={cardStyle}
      >
        <div className="flex items-start justify-between gap-3 mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Step {index + 1} of {steps.length}
          </span>
          <button
            onClick={handleClose}
            aria-label="Skip tour"
            className="p-1 -m-1 text-[var(--text-muted)] hover:text-[var(--text-primary)] bg-transparent border-0 cursor-pointer"
          >
            &times;
          </button>
        </div>

        <h3 className="text-[15px] font-semibold text-[var(--text-primary)] mb-1.5 tracking-tight">
          {step.title}
        </h3>
        <p className="text-[13px] text-[var(--text-secondary)] leading-relaxed m-0">
          {step.body}
        </p>

        <div className="flex items-center gap-1.5 mt-4 mb-3">
          {steps.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all duration-200 ${
                i === index ? 'w-5 bg-[var(--accent)]' : 'w-1.5 bg-[var(--border)]'
              }`}
            />
          ))}
        </div>

        <div className="flex items-center justify-between gap-2">
          <button
            onClick={handleClose}
            className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] bg-transparent border-0 p-0 cursor-pointer"
          >
            Skip tour
          </button>
          <div className="flex items-center gap-2">
            {index > 0 && (
              <button
                onClick={back}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-[var(--radius-sm)] border border-[var(--border)] text-[13px] text-[var(--text-secondary)] hover:bg-[var(--surface-raised)]"
              >
                Back
              </button>
            )}
            <button
              onClick={next}
              className="rounded-[var(--radius-sm)] bg-[var(--accent)] px-3.5 py-1.5 text-[13px] font-medium text-white hover:opacity-90"
            >
              {index >= steps.length - 1 ? 'Done' : 'Next'}
            </button>
          </div>
        </div>
        {screenAnnouncement && (
          <div aria-live="polite" className="sr-only" role="status">
            {screenAnnouncement}
          </div>
        )}
      </div>
    </div>
  );
}

export function tourSeen(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1';
  } catch {
    return true;
  }
}

export function markTourSeen(key: string): void {
  try {
    localStorage.setItem(key, '1');
  } catch {
    /* ignore */
  }
}
