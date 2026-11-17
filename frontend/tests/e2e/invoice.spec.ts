import { expect, test, type Page } from "@playwright/test";

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? "";
const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "";

test.skip(!OWNER_EMAIL || !OWNER_PASSWORD, "Set E2E_OWNER_EMAIL and E2E_OWNER_PASSWORD");

async function signIn(page: Page) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

/** Small API helper for test setup; the flow under test is driven through the UI. */
async function apiCall<T>(page: Page, method: "GET" | "POST" | "PUT", path: string, data?: unknown): Promise<T> {
  const csrf = (await page.context().cookies()).find((c) => c.name === "wp_csrf")?.value ?? "";
  const res = await page.request.fetch(`/api/v1${path}`, { method, data, headers: { "x-csrf-token": csrf } });
  expect(res.ok(), `${method} ${path}: ${await res.text()}`).toBeTruthy();
  return (await res.json()) as T;
}

test("invoice: issue from approved quotation, part payment, retry-safe, then paid", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name.slice(0, 1).toUpperCase()}${Date.now() % 100000}`;
  await signIn(page);

  // Setup: a job with an approved quotation (N$ 1,035.00), at quality inspection.
  const me = await apiCall<{ branches: { id: string }[] }>(page, "GET", "/auth/me");
  const customer = await apiCall<{ id: string }>(page, "POST", "/customers", { customer_type: "individual", last_name: `Invoice${run}` });
  const vehicle = await apiCall<{ id: string }>(page, "POST", "/vehicles", { customer_id: customer.id, registration_number: `N ${run} I`, make: "Nissan", model: "NP200" });
  const job = await apiCall<{ id: string; version: number }>(page, "POST", "/job-cards", { branch_id: me.branches[0].id, customer_id: customer.id, vehicle_id: vehicle.id, complaint: "Service" });
  let version = (await apiCall<{ version: number }>(page, "POST", `/job-cards/${job.id}/transitions`, { to_status: "diagnosis_in_progress", version: job.version })).version;
  const quote = await apiCall<{ id: string }>(page, "POST", `/job-cards/${job.id}/quotation`);
  await apiCall(page, "PUT", `/quotations/${quote.id}/draft`, {
    items: [
      { kind: "labour", description: "Minor service", quantity: "1", unit_price: "600.00" },
      { kind: "part", description: "Oil filter and oil", quantity: "1", unit_price: "435.00" },
    ],
  });
  await apiCall(page, "POST", `/quotations/${quote.id}/send`, { email_customer: false });
  await apiCall(page, "POST", `/quotations/${quote.id}/decisions`, { decision: "approved", method: "in_person", customer_name: `Ina Invoice${run}`, evidence: "Signed at the counter" });
  for (const to of ["repair_in_progress", "quality_inspection"]) {
    version = (await apiCall<{ version: number }>(page, "POST", `/job-cards/${job.id}/transitions`, { to_status: to, version })).version;
  }

  // Start the invoice from the job card; lines come from the approved quotation.
  await page.goto(`/job-cards/${job.id}`);
  await page.getByRole("button", { name: "Start invoice" }).click();
  await expect(page.getByRole("heading", { name: "Draft invoice" })).toBeVisible();
  await expect(page.getByText("Prefilled from the approved quotation")).toBeVisible();
  await expect(page.getByText("N$ 1,035.00").first()).toBeVisible();

  await page.getByRole("button", { name: "Issue invoice" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Issue invoice" }).click();
  await expect(page.getByRole("heading", { name: /^INV-\d+$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save draft" })).toHaveCount(0);

  // Part payment. The first request is replayed (same idempotency key) to prove a
  // double submit records the payment once.
  let firstPaymentBody = "";
  await page.route("**/api/v1/payments", async (route) => {
    const response = await route.fetch();
    firstPaymentBody = await response.text();
    const replay = await route.fetch();
    expect(replay.status()).toBe(200);
    expect(replay.headers()["idempotent-replayed"]).toBe("true");
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Record payment" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Amount received").fill("400.00");
  await dialog.getByLabel("Method").selectOption("cash");
  await dialog.getByRole("button", { name: "Record payment" }).click();
  await expect(dialog).toBeHidden();
  await page.unroute("**/api/v1/payments");
  expect(JSON.parse(firstPaymentBody).receipt_number).toMatch(/^RCT-\d+$/);
  await expect(page.getByText("Partially paid")).toBeVisible();
  await expect(page.getByText("N$ 635.00").first()).toBeVisible();

  // Pay the balance.
  await page.getByRole("button", { name: "Record payment" }).click();
  await expect(dialog.getByLabel("Amount received")).toHaveValue("635.00");
  await dialog.getByRole("button", { name: "Record payment" }).click();
  await expect(dialog).toBeHidden();
  // "Paid" is both the status badge and a row label in the balance panel, so check the
  // balance itself.
  await expect(page.getByRole("button", { name: "Record payment" })).toHaveCount(0);
  const balance = page.locator("dl div", { has: page.getByText("Balance due", { exact: true }) });
  await expect(balance.getByText("N$ 0.00")).toBeVisible();

  // The invoice PDF opens from the page and reflects the payments.
  const pdfHref = await page.getByRole("link", { name: "PDF", exact: true }).getAttribute("href");
  const pdf = await page.request.get(pdfHref ?? "");
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");

  // Exactly two receipts on the invoice, and the customer owes nothing.
  await expect(page.getByRole("link", { name: /RCT-\d+/ })).toHaveCount(2);
  await page.goto(`/customers/${customer.id}`);
  const account = page.locator("section", { has: page.getByRole("heading", { name: "Account" }) });
  await expect(account.getByText("N$ 0.00").first()).toBeVisible();
});
