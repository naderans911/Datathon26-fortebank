import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './e2e',
  testIgnore: 'local-review.spec.ts',
  fullyParallel: false,
  // The real API intentionally permits one synthetic media generation at a time.
  workers: process.env.LIVE_API_URL ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : undefined,
    channel:
      process.platform === 'win32' && !process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
        ? 'chrome'
        : undefined,
  },
  projects: [
    {
      name: 'desktop-chrome',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } },
    },
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: {
    command: 'npm run dev -- --port 5173 --strictPort',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: !process.env.CI,
  },
})
