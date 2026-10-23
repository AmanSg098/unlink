import { expect, test, type Browser, type Page } from "@playwright/test";

const PASSWORD = "unlink-demo"; // seeded dev accounts (apps/api/app/cli.py)
const MFA_ROLES = ["legal", "finance", "approver", "admin"];

/** Signs in through the UI. MFA roles get their current code from the development-only /api/dev/totp. */
async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  if (MFA_ROLES.includes(email.split("@")[0])) {
    await expect(page.getByRole("heading", { name: /Verify it.s you/ })).toBeVisible();
    const { code } = await (await page.request.get(`/api/dev/totp?email=${encodeURIComponent(email)}`)).json();
    await page.getByLabel("Authentication code").fill(code);
    await page.getByRole("button", { name: "Verify" }).click();
  }
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByRole("heading", { name: /Good (morning|afternoon|evening)/ })).toBeVisible();
}

async function asRole(browser: Browser, email: string, fn: (page: Page) => Promise<void>) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await signIn(page, email);
  await fn(page);
  await ctx.close();
}

/** Opens the decision dialog on a plan and approves the current step. */
async function approveStep(page: Page, url: string, comment: string) {
  await page.goto(url);
  await page.getByRole("button", { name: "Review & decide" }).click();
  const dialog = page.getByRole("dialog");
  const justification = dialog.getByLabel(/Fairness justification/);
  if (await justification.isVisible()) {
    await justification.fill("Flagged group is small; selection follows documented role criteria");
  }
  await dialog.getByLabel(/Comment/).fill(comment);
  await dialog.getByRole("button", { name: "Approve" }).click();
  await expect(dialog).toBeHidden();
}

test("landing page is public and links to sign in", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Hard decisions/ })).toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).first().click();
  await expect(page).toHaveURL(/\/login/);
});

test("signed-out users are sent to login", async ({ page }) => {
  await page.goto("/people");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill("hr@democorp.in");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Invalid email or password")).toBeVisible();
});

test("plan goes through legal, finance and final approval, then exit cases open", async ({ page, browser }) => {
  test.setTimeout(180_000);
  await signIn(page, "hr@democorp.in");
  await page.getByRole("link", { name: "New reduction plan" }).first().click();
  await page.getByLabel("Name").fill("E2E Support trim");
  await page.getByLabel("Business rationale").fill("Ticket volume moved to self-service");
  await page.getByLabel("Headcount target").fill("3");
  await page.getByRole("button", { name: "Support", exact: true }).click();
  await page.getByRole("button", { name: "Create draft" }).click();

  await expect(page.getByRole("heading", { name: "E2E Support trim" })).toBeVisible();
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByRole("button", { name: "Re-run" })).toBeVisible();

  // The defensibility pack downloads as a real PDF.
  const planId = page.url().split("/").pop();
  const pdf = await page.request.get(`/api/plans/${planId}/report.pdf`);
  expect(pdf.status()).toBe(200);
  expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");

  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByText(/you prepared this plan, so you can't approve it/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Review & decide" })).toHaveCount(0);
  const url = page.url();

  await asRole(browser, "legal@democorp.in", (p) => approveStep(p, url, "Reason codes and process reviewed"));
  await asRole(browser, "finance@democorp.in", (p) => approveStep(p, url, "Cost figures match payroll"));
  await asRole(browser, "approver@democorp.in", (p) => approveStep(p, url, "Approved after committee review"));

  await page.reload();
  await page.getByRole("tab", { name: "Exit cases" }).click();
  await page.getByRole("button", { name: "Open exit cases" }).click();
  const caseLinks = page.locator('a[href^="/cases/"]');
  await expect(caseLinks).toHaveCount(3);

  await caseLinks.first().click();
  await expect(page).toHaveURL(/\/cases\/\d+/);
  await expect(page.getByText("Reason and evidence")).toBeVisible();
  await expect(page.getByText("Notice and last working day")).toBeVisible();
});

test("roles shape the UI", async ({ page }) => {
  await signIn(page, "viewer@democorp.in");
  await expect(page.getByRole("link", { name: "New reduction plan" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Team & access" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Audit log" })).toHaveCount(0);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);

  await signIn(page, "admin@democorp.in");
  await page.getByRole("link", { name: "Team & access" }).click();
  await expect(page.getByText("hr@democorp.in")).toBeVisible();
});

test("legal sees unverified rules and an intact audit chain", async ({ page }) => {
  await signIn(page, "legal@democorp.in");
  await page.getByRole("link", { name: "Jurisdiction rules", exact: true }).click();
  await expect(page.getByText(/active rules are unverified/)).toBeVisible();
  await page.getByRole("link", { name: "Audit log", exact: true }).click();
  await page.getByRole("button", { name: /Verify chain/ }).click();
  await expect(page.getByText(/Intact/).first()).toBeVisible();
});

test("custom KPI can be previewed and created", async ({ page }) => {
  await signIn(page, "hr@democorp.in");
  await page.getByRole("link", { name: "KPI library" }).click();
  await page.getByLabel("Label").fill("Engagement");
  await page.getByLabel("Key").fill("engagement");
  await page.getByLabel("Formula").fill('metric("engagement_score", 3)');
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByText(/Evaluated for 250 employees/)).toBeVisible();
  await page.getByRole("button", { name: "Create KPI" }).click();
  await expect(page.getByText("Custom · hr@democorp.in")).toBeVisible();
});

test("command palette jumps to pages", async ({ page }) => {
  await signIn(page, "hr@democorp.in");
  await page.keyboard.press("ControlOrMeta+k");
  await page.getByPlaceholder(/Search plans/).fill("exit cases");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/cases/);
});
