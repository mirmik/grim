import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/android',
  outputDir: 'test-results/android',
  workers: 1,
  timeout: 30000,
  use: {baseURL: 'http://127.0.0.1:1420', viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true},
  webServer: {command: 'npm run preview:android', url: 'http://127.0.0.1:1420', reuseExistingServer: false},
});
