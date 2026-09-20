import { defineConfig, devices } from '@playwright/test';

/**
 * E2E configuration.
 *
 * The suite needs two things: a running backend (default http://127.0.0.1:8000)
 * and a served production build of the frontend.  `vite preview` starts the
 * frontend automatically and proxies `/api` to the backend, so the browser sees
 * a same-origin API and the session cookie stays first-party.
 *
 * Overridable for other setups:
 *   E2E_BASE_URL    frontend origin that Playwright drives (default http://localhost:4173)
 *   E2E_API_URL     backend used by the direct API assertions (default http://127.0.0.1:8000)
 *   E2E_NO_SERVER=1 skip starting `vite preview` (bring your own server)
 *
 * Why `localhost` and not `127.0.0.1`: `vite preview` binds the `localhost`
 * hostname only, so a 127.0.0.1 base URL is not reachable on Windows.  Both
 * spellings are normalised to `localhost` so either one can be passed in.
 */
function normaliseHost(rawUrl: string): string {
  return rawUrl.replace('//127.0.0.1', '//localhost');
}

const BASE_URL = normaliseHost(process.env.E2E_BASE_URL || 'http://localhost:4173');
const API_URL = process.env.E2E_API_URL || 'http://127.0.0.1:8000';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 20_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'mobile-chrome', use: { ...devices['Pixel 5'] } },
  ],
  webServer: process.env.E2E_NO_SERVER
    ? undefined
    : [
        {
          command: `npm run preview -- --port ${new URL(BASE_URL).port} --strictPort`,
          url: BASE_URL,
          reuseExistingServer: true,
          timeout: 120_000,
        },
      ],
  metadata: { apiUrl: API_URL },
});
