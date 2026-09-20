import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Same-origin API during development AND when previewing the production build,
// so the session cookie stays first-party (no CORS / SameSite surprises) and the
// Playwright suite can run against `vite preview` without a rebuild.
const apiProxy = {
  '/api': {
    target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: apiProxy,
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: apiProxy,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: { provider: 'v8', reporter: ['text', 'lcov'] },
  },
});
