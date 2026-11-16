import { expect, test, type Page } from "@playwright/test";

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? "";
const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "";

test.skip(!OWNER_EMAIL || !OWNER_PASSWORD, "Set E2E_OWNER_EMAIL and E2E_OWNER_PASSWORD");

async function apiCall<T>(page: Page, method: "GET" | "POST" | "PUT", path: string, data?: unknown, key?: string): Promise<T> {
  const csrf = (await page.context().cookies()).find((c) => c.name === "wp_csrf")?.value ?? "";
  const headers: Record<string, string> = { "x-csrf-token": csrf };
  if (key) headers["idempotency-key"] = key;
  const res = await page.request.fetch(`/api/v1${path}`, { method, data, headers });
  expect(res.ok(), `${method} ${path}: ${await res.text()}`).toBeTruthy();
  return (await res.json()) as T;
}

test("job parts: blocked until approved, reserve, issue, return", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name.slice(0, 1).toUpperCase()}${Date.now() % 100000}`;
  const sku = `JP-${run}`;
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // Setup: a stocked part and a job in diagnosis.
  const me = await apiCall<{ branches: { id: string }[] }>(page, "GET", "/auth/me");
  const part = await apiCall<{ id: string }>(page, "POST", "/inventory/parts", { sku, name: "Spark plug", selling_price: "95.00" });
  const locations = await apiCall<{ id: string; is_default: boolean; branch: { id: string } }[]>(page, "GET", "/inventory/locations");
  const main = locations.find((l) => l.is_default && l.branch.id === me.branches[0].id)!;
  await apiCall(page, "POST", "/inventory/adjustments", { location_id: main.id, reason: "Opening stock", lines: [{ part_id: part.id, counted: "8" }] }, crypto.randomUUID());
  const customer = await apiCall<{ id: string }>(page, "POST", "/customers", { customer_type: "individual", last_name: `Parts${run}` });
  const vehicle = await apiCall<{ id: string }>(page, "POST", "/vehicles", { customer_id: customer.id, registration_number: `N ${run} P`, make: "Mazda", model: "BT-50" });
  const job = await apiCall<{ id: string; version: number }>(page, "POST", "/job-cards", { branch_id: me.branches[0].id, customer_id: customer.id, vehicle_id: vehicle.id, complaint: "Misfire" });
  await apiCall(page, "POST", `/job-cards/${job.id}/transitions`, { to_status: "diagnosis_in_progress", version: job.version });

  // Not approved yet: no reserve/issue actions.
  await page.goto(`/job-cards/${job.id}`);
  await expect(page.getByText("Parts can be reserved and issued once the customer approves")).toBeVisible();
  await expect(page.getByRole("button", { name: "Issue parts" })).toHaveCount(0);

  // Customer approval recorded through an authorised exception.
  await apiCall(page, "POST", `/job-cards/${job.id}/approval-exceptions`, { exception_type: "customer_verbal", reason: "Customer phoned in", scope: "Replace spark plugs" });
  await page.reload();

  // Reserve 4.
  await page.getByRole("button", { name: "Reserve", exact: true }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByLabel("Search parts").fill(sku);
  await dialog.getByRole("button", { name: new RegExp(sku) }).click();
  await dialog.getByLabel("Quantity").fill("4");
  await dialog.getByRole("button", { name: "Reserve", exact: true }).click();
  await expect(dialog).toBeHidden();
  const reserved = page.getByRole("region", { name: "Reserved" });
  await expect(reserved.getByText(sku)).toBeVisible();

  // Issue 4 (uses the reservation).
  await page.getByRole("button", { name: "Issue parts" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Search parts").fill(sku);
  await dialog.getByRole("button", { name: new RegExp(sku) }).click();
  await dialog.getByLabel("Quantity").fill("4");
  await dialog.getByRole("button", { name: "Issue", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("region", { name: "Reserved" })).toHaveCount(0);
  const fitted = page.getByRole("region", { name: "Fitted" });
  await expect(fitted.getByText("N$ 380.00")).toBeVisible();

  // Return 1 unused.
  await fitted.getByRole("button", { name: "Return" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Quantity").fill("1");
  await dialog.getByLabel("Reason").fill("One plug was fine");
  await dialog.getByRole("button", { name: "Return", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(fitted.getByText("N$ 285.00")).toBeVisible();

  // Stock: 8 - 4 + 1 = 5.
  await page.goto(`/inventory/parts/${part.id}`);
  await expect(page.getByText("5 available").first()).toBeVisible();
});
