import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? "";
const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "";
const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

test.skip(!OWNER_EMAIL || !OWNER_PASSWORD, "Set E2E_OWNER_EMAIL and E2E_OWNER_PASSWORD");

async function apiCall<T>(page: Page, method: "GET" | "POST" | "PUT", path: string, data?: unknown): Promise<T> {
  const csrf = (await page.context().cookies()).find((c) => c.name === "wp_csrf")?.value ?? "";
  const res = await page.request.fetch(`/api/v1${path}`, { method, data, headers: { "x-csrf-token": csrf } });
  expect(res.ok(), `${method} ${path}: ${await res.text()}`).toBeTruthy();
  return (await res.json()) as T;
}

async function signInLink(request: APIRequestContext, to: string): Promise<string> {
  for (let attempt = 0; attempt < 30; attempt++) {
    const list = await (await request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`)).json();
    const id = list.messages?.[0]?.ID;
    if (id) {
      const message = await (await request.get(`${MAILPIT}/api/v1/message/${id}`)).json();
      const match = /(https?:\/\/\S+\/portal\/auth#token=[\w-]+)/.exec(message.Text as string);
      if (match) return new URL(match[1]).pathname + new URL(match[1]).hash;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`No portal email for ${to}`);
}

test("customer portal: invited by email, follows the job and approves the quotation", async ({ page, browser, request }, testInfo) => {
  const run = `${testInfo.project.name.slice(0, 1).toLowerCase()}${Date.now() % 100000}`;
  const email = `portal-${run}@example.com`;
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill(OWNER_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // Staff: customer, vehicle, job with a sent quotation.
  const me = await apiCall<{ branches: { id: string }[] }>(page, "GET", "/auth/me");
  const customer = await apiCall<{ id: string }>(page, "POST", "/customers", { customer_type: "individual", last_name: `Portal${run}`, contacts: [{ kind: "email", value: email }] });
  const vehicle = await apiCall<{ id: string }>(page, "POST", "/vehicles", { customer_id: customer.id, registration_number: `N ${run.toUpperCase()} P`, make: "Isuzu", model: "D-Max" });
  const job = await apiCall<{ id: string; version: number }>(page, "POST", "/job-cards", { branch_id: me.branches[0].id, customer_id: customer.id, vehicle_id: vehicle.id, complaint: "Clutch slipping" });
  await apiCall(page, "POST", `/job-cards/${job.id}/transitions`, { to_status: "diagnosis_in_progress", version: job.version });
  const q = await apiCall<{ id: string }>(page, "POST", `/job-cards/${job.id}/quotation`);
  await apiCall(page, "PUT", `/quotations/${q.id}/draft`, { items: [{ kind: "labour", description: "Replace clutch kit", quantity: "4", unit_price: "500.00" }] });
  await apiCall(page, "POST", `/quotations/${q.id}/send`, { email_customer: false });

  // Staff gives portal access from the customer page.
  await page.goto(`/customers/${customer.id}`);
  await page.getByRole("button", { name: "Give portal access" }).click();
  await expect(page.getByText(`Sign-in link sent to ${email}.`)).toBeVisible();
  const link = await signInLink(request, email);

  // Customer: separate browser, no staff session.
  const portal = await (await browser.newContext()).newPage();
  await portal.goto("/portal");
  await expect(portal).toHaveURL(/\/portal\/sign-in$/);
  await portal.goto(link);
  await expect(portal.getByRole("heading", { name: `Hello Portal${run}` })).toBeVisible();
  await expect(portal.getByText("Diagnosis in progress")).toBeVisible();

  // Approve the quotation.
  await portal.getByRole("link", { name: /^QT-\d+/ }).click();
  await expect(portal.getByText("N$ 2,000.00").first()).toBeVisible();
  await expect(portal.getByRole("button", { name: "Approve quotation" })).toBeDisabled();
  await portal.getByLabel("I accept this quotation, its total and its terms").check();
  await portal.getByRole("button", { name: "Approve quotation" }).click();
  await expect(portal.getByText(/^You approved this quotation/)).toBeVisible();

  // The workshop sees the approval at once.
  const detail = await apiCall<{ approval_status: string }>(page, "GET", `/job-cards/${job.id}`);
  expect(detail.approval_status).toBe("quotation_approved");

  // The customer opts in to WhatsApp updates.
  await portal.getByRole("link", { name: "My details" }).click();
  await portal.getByLabel("Send me updates by WhatsApp").check();
  await portal.getByRole("button", { name: "Save" }).click();
  await expect(portal.getByText("Saved.")).toBeVisible();
  const consents = await apiCall<{ channel: string; status: string; method: string }[]>(page, "GET", `/customers/${customer.id}/consents`);
  expect(consents[0]).toMatchObject({ channel: "whatsapp", status: "granted", method: "customer_portal" });

  // Request a booking for tomorrow; the workshop confirms it.
  const tomorrow = new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Windhoek" }).format(new Date(Date.now() + 86_400_000));
  await portal.getByRole("link", { name: "Bookings" }).click();
  await portal.getByLabel("Preferred day").fill(tomorrow);
  await portal.getByLabel("Time of day").selectOption("afternoon");
  await portal.getByLabel("What do you need?").fill(`Aircon not cold ${run}`);
  await portal.getByRole("button", { name: "Request booking" }).click();
  await expect(portal.getByText("Waiting for the workshop")).toBeVisible();

  await page.goto("/appointments");
  const bookingRequest = page.locator("li", { hasText: `Aircon not cold ${run}` });
  await bookingRequest.getByRole("button", { name: "Confirm" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Start")).toHaveValue("13:00");
  await dialog.getByRole("button", { name: "Book appointment" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.locator("li", { hasText: `Aircon not cold ${run}` })).toHaveCount(0);

  await portal.reload();
  await expect(portal.getByText("Booked", { exact: true })).toBeVisible();

  // Signing out ends the session.
  await portal.getByRole("button", { name: "Sign out" }).click();
  await expect(portal).toHaveURL(/\/portal\/sign-in$/);
  await portal.goto("/portal");
  await expect(portal).toHaveURL(/\/portal\/sign-in$/);
});
