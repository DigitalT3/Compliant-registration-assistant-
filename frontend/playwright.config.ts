import { defineConfig, devices } from "@playwright/test";

/**
 * Browser acceptance configuration for the synthetic-data PoC.
 *
 * The backend receives a test-only SQLite path, preventing the browser suite
 * from using a developer's local demonstrator database.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5183",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      // Uses the Chrome already installed on the machine; no browser download is needed.
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],
  webServer: [
    {
      // Fresh synthetic database for every run, so the scripted cases are deterministic.
      command: "export POC_DB=sqlite POC_DB_PATH=frontend/.playwright-poc.sqlite3 && .venv/bin/python -m backend.seed --reset && .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8010",
      cwd: "..",
      url: "http://127.0.0.1:8010/health",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      // Odd ports so the suite never collides with another dev server on 8000/5173.
      command: "BACKEND_URL=http://127.0.0.1:8010 npx vite --host 127.0.0.1 --port 5183 --strictPort",
      url: "http://127.0.0.1:5183",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
