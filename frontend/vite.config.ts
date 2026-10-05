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
  },
});
