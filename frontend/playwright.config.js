import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 10000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: { args: ['--disable-gpu'] },
  },
  webServer: [
    {
      command: 'uv run --directory ../backend python -m devtools.ui_server --port 8011',
      url: 'http://127.0.0.1:8011/api/health',
      timeout: 60000,
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 4173',
      url: 'http://127.0.0.1:4173',
      timeout: 60000,
      reuseExistingServer: false,
      env: {
        VITE_API_BASE_URL: 'http://127.0.0.1:8011/api',
        VITE_DEMO_MODE: 'true',
      },
    },
  ],
})
