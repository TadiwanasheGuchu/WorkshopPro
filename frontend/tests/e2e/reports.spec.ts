import { expect, test } from "@playwright/test";

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? "";
const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "";

test.skip(!OWNER_EMAIL || !OWNER_PASSWORD, "Set E2E_OWNER_EMAIL and E2E_OWNER_PASSWORD");

test("reports: financial and operations with explicit periods", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Reports", level: 1 })).toBeVisible();
  // Invoiced and cash are reported separately; receivables are labelled as at today.
  await expect(page.getByRole("term").filter({ hasText: /^Net invoiced$/ })).toBeVisible();
  await expect(page.getByRole("term").filter({ hasText: /^Net received$/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Receivables as at / })).toBeVisible();

  await page.getByRole("link", { name: "Last month" }).click();
  await expect(page).toHaveURL(/from=\d{4}-\d{2}-01/);
  await expect(page.getByRole("link", { name: "Last month" })).toHaveAttribute("aria-current", "true");

  await page.getByRole("link", { name: "Operations" }).click();
  await expect(page.getByRole("heading", { name: "Open jobs now" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Mechanic workload" })).toBeVisible();
  await page.getByText("How these figures are calculated").click();
  await expect(page.getByText("Time from vehicle received to completed")).toBeVisible();

  await page.getByRole("link", { name: "Inventory", exact: true }).click();
  await expect(page.getByRole("heading", { name: /^Stock value as at / })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Stock check" })).toBeVisible();
  await expect(page.getByText("Stock matches the ledger")).toBeVisible();
});
