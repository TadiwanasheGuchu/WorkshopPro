import { expect, test, type Page } from "@playwright/test";

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? "";
const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "";

test.skip(!OWNER_EMAIL || !OWNER_PASSWORD, "Set E2E_OWNER_EMAIL and E2E_OWNER_PASSWORD");

async function apiCall<T>(page: Page, method: "GET" | "POST", path: string, data?: unknown): Promise<T> {
  const csrf = (await page.context().cookies()).find((c) => c.name === "wp_csrf")?.value ?? "";
  const res = await page.request.fetch(`/api/v1${path}`, { method, data, headers: { "x-csrf-token": csrf } });
  expect(res.ok(), `${method} ${path}: ${await res.text()}`).toBeTruthy();
  return (await res.json()) as T;
}

test("purchasing: supplier, order, approve, partial delivery, complete", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name.slice(0, 1).toUpperCase()}${Date.now() % 100000}`;
  const sku = `PO-${run}`;
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  const part = await apiCall<{ id: string }>(page, "POST", "/inventory/parts", { sku, name: "Air filter", cost_price: "120.00" });

  // Add a supplier.
  await page.goto("/suppliers/new");
  await page.getByLabel("Name").fill(`Namib Spares ${run}`);
  await page.getByLabel("Phone").fill("061 555 0101");
  await page.getByLabel("Our account number").fill("NS-4410");
  await page.getByRole("button", { name: "Add supplier" }).click();
  await expect(page.getByRole("heading", { name: `Namib Spares ${run}` })).toBeVisible();

  // Start an order and add a line.
  await page.getByRole("button", { name: "New purchase order" }).click();
  const dialog = page.getByRole("dialog");
  if (await dialog.isVisible().catch(() => false)) await dialog.getByRole("button", { name: "Start order" }).click();
  await expect(page.getByRole("heading", { name: /^PO-\d+$/ })).toBeVisible();
  await page.getByLabel("Search parts").fill(sku);
  await page.getByRole("button", { name: new RegExp(sku) }).click();
  await page.getByLabel("Line 1 quantity").fill("10");
  await page.getByLabel("Line 1 unit cost").fill("115.00");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText("N$ 1,150.00").first()).toBeVisible();

  // Approve.
  await page.getByRole("button", { name: "Approve order" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("button", { name: "Receive delivery" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve order" })).toHaveCount(0);

  // Partial delivery: 6 of 10.
  await page.getByRole("button", { name: "Receive delivery" }).click();
  let d = page.getByRole("dialog");
  await expect(d.getByLabel(`${sku} received`)).toHaveValue("10");
  await d.getByLabel(`${sku} received`).fill("6");
  await d.getByLabel("Delivery note").fill(`DN-${run}`);
  await d.getByLabel(`${sku} discrepancy note`).fill("4 back-ordered");
  await d.getByRole("button", { name: "Record delivery" }).click();
  await expect(d).toBeHidden();
  await expect(page.getByText("Partly received", { exact: true })).toBeVisible();
  await expect(page.getByText("4 back-ordered")).toBeVisible();

  // The rest arrives.
  await page.getByRole("button", { name: "Receive delivery" }).click();
  d = page.getByRole("dialog");
  await expect(d.getByLabel(`${sku} received`)).toHaveValue("4");
  await d.getByRole("button", { name: "Record delivery" }).click();
  await expect(d).toBeHidden();
  await expect(page.getByRole("heading", { name: "Deliveries received" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Receive delivery" })).toHaveCount(0);

  // Stock and cost price follow the deliveries.
  const after = await apiCall<{ cost_price: string; stock: { on_hand: string } }>(page, "GET", `/inventory/parts/${part.id}`);
  expect(after.stock.on_hand).toBe("10.00");
  expect(after.cost_price).toBe("115.00");
});
