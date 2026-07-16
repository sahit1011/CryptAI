import { defineConfig } from "@playwright/test";

/**
 * E2E against a RUNNING stack (frontend + backend + auth) — not mocked.
 * Point E2E_BASE_URL at the deployment (default: the local docker stack).
 * Credentials come from E2E_EMAIL / E2E_PASSWORD (default: the demo account).
 *
 * Run: npm run test:e2e
 */
export default defineConfig({
    testDir: "./e2e",
    timeout: 45_000,
    retries: 1,
    workers: 1, // one session; auth state is shared
    use: {
        baseURL: process.env.E2E_BASE_URL || "http://localhost:3010",
        screenshot: "only-on-failure",
        trace: "retain-on-failure",
    },
    reporter: [["list"]],
});
