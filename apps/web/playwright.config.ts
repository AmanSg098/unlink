import { defineConfig, devices } from "@playwright/test";

// Smoke tests run against a throwaway API database (data/e2e.db) on port 8001 and a production
// build on port 3101, so they never touch the dev servers or dev data.
const E2E_DB = "sqlite:///data/e2e.db";
const API_ENV = `DATABASE_URL=${E2E_DB} DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`;

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  use: { baseURL: "http://localhost:3101", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command:
        `cd ../api && rm -f data/e2e.db && ${API_ENV} uv run alembic upgrade head && ` +
        `${API_ENV} uv run python -m app.cli seed && ${API_ENV} uv run uvicorn app.main:app --port 8001`,
      url: "http://127.0.0.1:8001/api/health",
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command:
        "NEXT_DIST_DIR=.next-e2e API_URL=http://127.0.0.1:8001 npm run build && " +
        "NEXT_DIST_DIR=.next-e2e API_URL=http://127.0.0.1:8001 npm run start -- -p 3101",
      url: "http://localhost:3101/login",
      timeout: 300_000,
      reuseExistingServer: false,
    },
  ],
});
