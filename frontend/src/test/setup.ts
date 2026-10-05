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