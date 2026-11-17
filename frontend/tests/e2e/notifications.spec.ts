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

test("notifications: vehicle received is sent in the background and logged", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name.slice(0, 1).toUpperCase()}${Date.now() % 100000}`;
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  const me = await apiCall<{ branches: { id: string }[] }>(page, "GET", "/auth/me");
  const customer = await apiCall<{ id: string }>(page, "POST", "/customers", {
    customer_type: "individual",
    last_name: `Notify${run}`,
    contacts: [{ kind: "email", value: `notify-${run.toLowerCase()}@example.com` }],
    preferred_contact_method: "email",
  });
  const vehicle = await apiCall<{ id: string }>(page, "POST", "/vehicles", { customer_id: customer.id, registration_number: `N ${run} M`, make: "Ford", model: "Ranger" });
  await apiCall(page, "POST", "/job-cards", { branch_id: me.branches[0].id, customer_id: customer.id, vehicle_id: vehicle.id, complaint: "Service" });

  // Delivery happens in the background; the log shows it once sent.
  await page.goto(`/notifications?customer=${customer.id}`);
  await expect(async () => {
    await page.reload();
    await expect(page.getByText("Sent", { exact: true })).toBeVisible({ timeout: 1000 });
  }).toPass({ timeout: 30_000 });
  await expect(page.getByText(`Email to notify-${run.toLowerCase()}@example.com`)).toBeVisible();
  await page.getByText("Message", { exact: true }).first().click();
  await expect(page.getByText(`We have received your vehicle N ${run} M Ford Ranger`)).toBeVisible();

  // Templates are listed with their placeholders.
  await page.getByRole("link", { name: "Message templates" }).click();
  await expect(page.getByRole("heading", { name: "Ready for collection" })).toBeVisible();
  await expect(page.getByText("{customer_name}").first()).toBeVisible();
});
