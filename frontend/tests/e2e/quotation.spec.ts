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

test("quotation: prepare, send, customer approves online, repair unlocks", async ({ page, browser, request }, testInfo) => {
  const run = `${testInfo.project.name.slice(0, 1).toUpperCase()}${Date.now() % 100000}`;
  await signIn(page);

  // Tax rate is configured by the workshop (none is assumed).
  const rates = await (await page.request.get("/api/v1/organisation/tax-rates")).json();
  if (!rates.some((r: { name: string }) => r.name === "Standard E2E")) {
    const csrf = (await page.context().cookies()).find((c) => c.name === "wp_csrf")?.value ?? "";
    await page.request.post("/api/v1/organisation/tax-rates", {
      data: { name: "Standard E2E", rate_percent: "15", is_default: true },
      headers: { "x-csrf-token": csrf },
    });
  }
  void request;

  // Customer, vehicle, job.
  await page.goto("/customers/new");
  await page.getByLabel("Surname").fill(`Quote${run}`);
  await page.getByRole("button", { name: "Register customer" }).click();
  await page.getByRole("link", { name: "Add vehicle" }).click();
  await page.getByLabel("Registration number").fill(`N ${run} Q`);
  await page.getByLabel("Make").fill("Toyota");
  await page.getByLabel("Model", { exact: true }).fill("Corolla");
  await page.getByRole("button", { name: "Register vehicle" }).click();
  await page.getByRole("link", { name: "Receive vehicle" }).click();
  await page.getByLabel("Customer complaint").fill("Brakes squeal");
  await page.getByRole("button", { name: "Open job card" }).click();
  await expect(page.getByRole("heading", { name: /^JC-\d+$/ })).toBeVisible();
  const jobUrl = page.url();
  await page.getByRole("button", { name: "Start diagnosis" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Start diagnosis" }).click();
  await expect(page.getByRole("button", { name: "Start repair" })).toBeDisabled();

  // Prepare the quotation.
  await page.getByRole("button", { name: "Prepare quotation" }).click();
  await expect(page.getByRole("heading", { name: /QT-\d+ · version 1/ })).toBeVisible();
  await page.getByRole("button", { name: "Labour" }).click();
  await page.getByLabel("Line 1 description").fill("Replace front brake pads");
  await page.getByLabel("Line 1 hours").fill("1.5");
  await page.getByLabel("Line 1 rate per hour").fill("450.00");
  await page.getByRole("button", { name: "Part" }).click();
  await page.getByLabel("Line 2 description").fill("Brake pad set");
  await page.getByLabel("Line 2 unit price").fill("890.00");
  await page.getByLabel("Line 2 tax").selectOption({ label: "Standard E2E (15.00%)" });
  await page.getByLabel("Line 1 tax").selectOption({ label: "Standard E2E (15.00%)" });
  await page.getByRole("button", { name: "Save draft" }).click();
  // 675.00 + 890.00 = 1565.00 + 15% = 1799.75, calculated by the server.
  await expect(page.getByText("N$ 1,799.75").first()).toBeVisible();

  // Send and take the customer link.
  await page.getByRole("button", { name: "Send to customer" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Send", exact: true }).click();
  const link = await page.getByLabel("Customer link").inputValue();
  expect(link).toContain("/quote#token=");
  await page.getByRole("dialog").getByRole("button", { name: "Done" }).click();

  // The customer opens the link (no sign-in). Opening it is not approval.
  const customer = await (await browser.newContext()).newPage();
  await customer.goto(new URL(link).pathname + new URL(link).hash);
  await expect(customer.getByText("N$ 1,799.75").first()).toBeVisible();
  await page.goto(jobUrl);
  await expect(page.getByRole("button", { name: "Start repair" })).toBeDisabled();

  const [download] = await Promise.all([customer.waitForEvent("download"), customer.getByRole("button", { name: "Download PDF" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^QT-\d+-v1\.pdf$/);

  await customer.getByLabel("Your full name").fill(`Selma Quote${run}`);
  await customer.getByRole("checkbox").check();
  await customer.getByRole("button", { name: "Approve quotation" }).click();
  await expect(customer.getByText("You approved this quotation")).toBeVisible();

  // Back in the workshop: approval recorded, repair can start without an exception.
  await page.reload();
  await expect(page.getByText("Quotation approved by customer")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start repair" })).toBeEnabled();
});
