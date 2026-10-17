// Shared PostHog loader. Single source of truth for the lazy import + init,
// so the boilerplate isn't duplicated across components and — critically —
// init happens *inside* the same promise the callers chain their capture()
// off, eliminating the init-vs-capture race.

let _posthog: Promise<typeof import('posthog-js').default> | null = null;
let _initialized = false;

/**
 * Lazily load PostHog, initialising it exactly once. Any `.capture()` chained
 * off the returned promise is guaranteed to run after `init()` because init is
 * performed synchronously inside this promise before the client is returned.
 *
 * No-op-safe: callers still guard on `import.meta.env.VITE_POSTHOG_KEY`, and if
 * the key is unset the client loads but is never initialised, so captures drop.
 */
export function getPosthog() {
  if (!_posthog) {
    _posthog = import('posthog-js').then(({ default: posthog }) => {
      const key = import.meta.env.VITE_POSTHOG_KEY;
      if (key && !_initialized) {
        posthog.init(key, {
          api_host: import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
          person_profiles: 'identified_only',
        });
        _initialized = true;
      }
      return posthog;
    });
  }
  return _posthog;
}
