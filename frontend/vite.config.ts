import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Same-origin in production (the FastAPI app serves frontend/dist). In local
// dev, proxy /api to the backend running on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // jsdom workers are memory-hungry; the default pool size (one per core)
    // times out unrelated tests on 6-8 GB agent hosts. Four workers keeps the
    // suite deterministic without skipping anything.
    maxWorkers: 4,
    minWorkers: 1,
    // Navigation-enumeration tests render every destination and legitimately
    // exceed the 5 s default on a loaded agent host.
    testTimeout: 15000,
    hookTimeout: 15000,
  },
});
