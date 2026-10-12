import { defineConfig, devices } from '@playwright/test';

// Cloud sessions use the pre-installed Chromium (PLAYWRIGHT_BROWSERS_PATH); never run `playwright install`.
const executablePath = process.env.SYSTEM_DESIGNER_CHROMIUM || undefined;

export default defineConfig({
  testDir: './tests/e2e',
  forbidOnly: !!process.env.CI,
  use: { trace: 'retain-on-failure', launchOptions: { executablePath } },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
