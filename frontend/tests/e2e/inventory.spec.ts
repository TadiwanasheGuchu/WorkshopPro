import { expect, test } from "@playwright/test";

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? "";
const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "";

test.skip(!OWNER_EMAIL || !OWNER_PASSWORD, "Set E2E_OWNER_EMAIL and E2E_OWNER_PASSWORD");

test("inventory: add part, opening count, minimum, transfer, ledger", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name.slice(0, 1).toUpperCase()}${Date.now() % 100000}`;
  const sku = `E2E-${run}`;
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // A second location to transfer into.
  await page.goto("/inventory/locations");
  await page.getByRole("button", { name: "Add location" }).click();
  await page.getByRole("dialog").getByLabel("Name").fill(`Van ${run}`);
  await page.getByRole("dialog").getByRole("button", { name: "Add location" }).click();
  await expect(page.getByText(`Van ${run}`)).toBeVisible();

  // Add a part.
  await page.goto("/inventory/parts/new");
  await page.getByLabel("SKU").fill(sku);
  await page.getByLabel("Name").fill("Oil filter");
  await page.getByLabel("Or new category").fill(`Filters ${run}`);
  await page.getByLabel("Cost price").fill("85.00");
  await page.getByLabel("Selling price").fill("140.00");
  await page.getByRole("button", { name: "Add part" }).click();
  await expect(page.getByRole("heading", { name: `${sku} · Oil filter` })).toBeVisible();

  // Opening count at the main store.
  const main = page.locator("li", { hasText: "Main store" }).first();
  await main.getByRole("button", { name: "Count / adjust" }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("Quantity counted").fill("6");
  await dialog.getByLabel("Reason").fill("Opening stock");
  await dialog.getByRole("button", { name: "Record adjustment" }).click();
  await expect(dialog).toBeHidden();
  await expect(main.getByText("6 available")).toBeVisible();

  // Whole units only.
  await main.getByRole("button", { name: "Count / adjust" }).click();
  await dialog.getByLabel("Quantity counted").fill("2.5");
  await expect(dialog.getByText("counted in whole units")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();

  // Transfer 2 to the van.
  await main.getByRole("button", { name: "Transfer" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("To").selectOption({ label: `Main branch · Van ${run}` });
  await dialog.getByLabel("Quantity").fill("2");
  await dialog.getByRole("button", { name: "Transfer" }).click();
  await expect(dialog).toBeHidden();
  await expect(main.getByText("4 available")).toBeVisible();

  // Minimum above available → low stock.
  await main.getByRole("button", { name: "Minimum" }).click();
  await page.getByRole("dialog").getByLabel("Minimum quantity").fill("5");
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(main.getByText("Low stock")).toBeVisible();
  await page.goto("/inventory/parts?low=1");
  await expect(page.getByRole("link", { name: new RegExp(sku) })).toBeVisible();

  // The ledger shows every movement.
  await page.goto("/inventory/movements");
  const rows = page.getByRole("row", { name: new RegExp(sku) });
  await expect(rows).toHaveCount(3);
  await expect(rows.filter({ hasText: "Opening stock" })).toHaveCount(1);
  await expect(rows.filter({ hasText: "Transfer out" })).toHaveCount(1);
  await expect(rows.filter({ hasText: "Transfer in" })).toHaveCount(1);
});
