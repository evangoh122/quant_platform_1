/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Geist"', '"Segoe UI Variable"', '"SF Pro Display"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', '"Geist Mono"', '"Fira Code"', 'ui-monospace', 'monospace'],
      },
      // The type scale lives in index.css so text-* class names stay stable
      // while the scale can be tuned at the root (HIG typography.md).
      fontSize: {
        xs: ['var(--text-xs)', { lineHeight: 'var(--leading-xs)' }],
        sm: ['var(--text-sm)', { lineHeight: 'var(--leading-sm)' }],
        base: ['var(--text-base)', { lineHeight: 'var(--leading-base)' }],
        lg: ['var(--text-lg)', { lineHeight: 'var(--leading-lg)' }],
        xl: ['var(--text-xl)', { lineHeight: 'var(--leading-xl)' }],
        '2xl': ['var(--text-2xl)', { lineHeight: 'var(--leading-2xl)' }],
        '3xl': ['var(--text-3xl)', { lineHeight: 'var(--leading-3xl)' }],
      },
    },
  },
  plugins: [],
};
