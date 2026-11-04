import { defineConfig } from "@playwright/test";

// The API runs on an in-memory database with test tenants and no AI key, so these tests are self-contained and never touch a real model or a real database.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:3100", trace: "retain-on-failure" },
  globalSetup: "./e2e/global-setup.ts",
  webServer: [
    {
      command: "cd .. && PYTHONPATH=kernel:ml:screening:lab SAFEPAY_TENANTS='e2e:e2e-admin:admin,e2e:e2e-viewer:viewer,empty:empty-key:admin' SAFEPAY_RATE_PER_S=0 SAFEPAY_CORS_ORIGINS=http://localhost:3100 OLLAMA_API_KEY= .venv/bin/uvicorn --factory safepay.api:create_app --port 8100",
      url: "http://127.0.0.1:8100/healthz",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    { command: "npm run build && npx next start -p 3100", url: "http://localhost:3100", reuseExistingServer: false, timeout: 180_000 },
  ],
});
