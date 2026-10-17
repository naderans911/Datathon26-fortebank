import { defineConfig, devices } from '@playwright/test'
import { resolve } from 'node:path'

// Builds and uses an isolated synthetic fixture server; never points at organizer records.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'local-review.spec.ts',
  workers: 1,
  reporter: 'list',
  outputDir: 'test-results-review',
  use: {
    baseURL: 'http://127.0.0.1:8001',
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
    command: `"${resolve('..', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')}" -m backend.tests.review_fixture`,
    cwd: resolve('..'),
    url: 'http://127.0.0.1:8001/review',
    reuseExistingServer: false,
    timeout: 60000,
  },
})
