import '@testing-library/jest-dom/vitest';

// jsdom does not implement scrollIntoView
HTMLElement.prototype.scrollIntoView = HTMLElement.prototype.scrollIntoView ?? (() => {});

// jsdom does not implement scrollTo
HTMLElement.prototype.scrollTo = HTMLElement.prototype.scrollTo ?? (() => {});

// jsdom does not implement matchMedia
if (!window.matchMedia) {
  window.matchMedia = window.matchMedia ?? (() => ({
    matches: false,
    media: '',
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
}

// Polyfill localStorage when not available (e.g. node without --localstorage-file)
if (typeof window.localStorage === 'undefined') {
  const store: Record<string, string> = {};
  (window as unknown as Record<string, unknown>).localStorage = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = String(value); },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { for (const key in store) delete store[key]; },
    get length() { return Object.keys(store).length; },
    key: (index: number) => Object.keys(store)[index] ?? null,
  };
}