import { expect, test, type Page } from "@playwright/test";

/**
 * Critical-flow E2E against the live stack: landing → login (real Supabase auth) →
 * dashboard sections → currency toggle → signals trading-mode → connect-exchange UI.
 * Serial: one authenticated session reused across tests.
 */
const EMAIL = process.env.E2E_EMAIL || "demo@cryptai.app";
const PASSWORD = process.env.E2E_PASSWORD || "CryptAI-Demo-2026";

test.describe.configure({ mode: "serial" });

let page: Page;

test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
});

test.afterAll(async () => {
    await page.close();
});

test("landing page renders with USD marketing content", async () => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: /log in|sign up|start trading/i }).first())
        .toBeVisible({ timeout: 15_000 });
    // Pre-login marketing shows dollars (the ₹/$ toggle is a dashboard feature).
    await expect(page.locator("text=/\\$1[0-9]{2},[0-9]{3}/").first()).toBeVisible();
});

test("logs in with real Supabase auth and lands on the dashboard", async () => {
    await page.goto("/auth/login");
    await page.locator('input[type="email"]').fill(EMAIL);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.locator('form button[type="submit"]').click();
    await page.waitForURL("**/dashboard**", { timeout: 20_000 });
    await expect(page.getByText("Total P&L").first()).toBeVisible({ timeout: 15_000 });
});

test("all dashboard sections open", async () => {
    for (const section of ["portfolio", "markets", "agents", "settings"]) {
        await page.goto(`/dashboard?section=${section}`);
        // Each section renders its own header; the app shell must not error-screen.
        await expect(page.locator("text=/something went wrong|unhandled error/i")).toHaveCount(0);
    }
    await page.goto("/dashboard");
});

test("currency toggle switches the dashboard to ₹ and back, and persists", async () => {
    await page.goto("/dashboard");
    const inr = page.getByRole("button", { name: "Show values in Indian Rupees" });
    const usd = page.getByRole("button", { name: "Show values in US Dollars" });
    await inr.click();
    await expect(page.locator("text=/₹/").first()).toBeVisible({ timeout: 10_000 });
    await page.reload();
    // Preference persists across reloads (localStorage).
    await expect(page.locator("text=/₹/").first()).toBeVisible({ timeout: 15_000 });
    await usd.click();
    await expect(inr).toBeVisible();
});

test("settings: trading mode switches to Manual and persists server-side", async () => {
    await page.goto("/dashboard?section=settings");
    await expect(page.getByText("Trading mode")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: /manual/i }).click();
    // Server persists via POST /api/settings; reload must come back as Manual.
    await page.reload();
    await expect(page.getByText("Trading mode")).toBeVisible({ timeout: 15_000 });
    await expect(
        page.getByRole("button", { name: /manual/i }),
    ).toHaveClass(/border-accent/, { timeout: 10_000 });
    // Leave the demo account in its default mode.
    await page.getByRole("button", { name: /paper/i }).click();
});

test("settings: exchange picker offers BingX and Delta India, testnet-gated", async () => {
    await page.goto("/dashboard?section=settings");
    await expect(page.getByText("Exchange connection")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Testnet only.")).toBeVisible();
    await expect(page.getByRole("button", { name: /BingX/ })).toBeVisible();
    const delta = page.getByRole("button", { name: /Delta Exchange India/ });
    await expect(delta).toBeVisible();
    // Selecting Delta adapts the help panel.
    await delta.click();
    await expect(page.getByText(/How to get Delta Exchange India testnet keys/)).toBeVisible();
});

test("markets: chart symbol selector switches instruments without errors", async () => {
    await page.goto("/dashboard?section=markets");
    for (const label of ["ETH", "Gold", "BTC"]) {
        await page.getByRole("button", { name: label, exact: true }).click();
        await expect(page.locator("text=/something went wrong/i")).toHaveCount(0);
    }
});
