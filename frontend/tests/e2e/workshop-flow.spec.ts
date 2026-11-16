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

test("customer → vehicle → receive → inspect → assign mechanic", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name.slice(0, 1).toUpperCase()}${Date.now() % 100000}`;
  const surname = `Flow${run}`;
  const plate = `N ${run} W`;
  await signIn(page);

  // Register the customer.
  await page.goto("/customers/new");
  await page.getByLabel("First name").fill("Selma");
  await page.getByLabel("Surname").fill(surname);
  await page.getByLabel("Contact 1", { exact: true }).fill("081 555 0101");
  await page.getByRole("button", { name: "Register customer" }).click();
  await expect(page.getByRole("heading", { name: `Selma ${surname}` })).toBeVisible();

  // Register the vehicle from the customer page.
  await page.getByRole("link", { name: "Add vehicle" }).click();
  await page.getByLabel("Registration number").fill(plate);
  await page.getByLabel("Make").fill("Ford");
  await page.getByLabel("Model", { exact: true }).fill("Ranger");
  await page.getByLabel("Odometer (km)").fill("64000");
  await page.getByRole("button", { name: "Register vehicle" }).click();
  await expect(page.getByRole("heading", { name: plate })).toBeVisible();

  // Receive the vehicle: opens a job card.
  await page.getByRole("link", { name: "Receive vehicle" }).click();
  await page.getByLabel("Customer complaint").fill("Steering pulls to the left");
  await page.getByLabel("Odometer at intake (km)").fill("64120");
  await page.getByRole("button", { name: "Open job card" }).click();
  await expect(page.getByRole("heading", { name: /^JC-\d+$/ })).toBeVisible();
  const jobUrl = page.url();

  // Intake inspection with a failed item and a note, then submit.
  await page.getByRole("button", { name: "Start inspection" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Start" }).click();
  await expect(page.getByText(/of \d+ checked/)).toBeVisible();
  await page.getByRole("radiogroup", { name: "Result for Front left tyre" }).getByRole("radio", { name: "Fail" }).click();
  await page.getByLabel("Notes for Front left tyre").fill("Inner edge worn to the cords");
  await page.getByLabel("Notes for Front left tyre").blur();
  await page.getByRole("radiogroup", { name: "Result for Steering play" }).getByRole("radio", { name: "Attention" }).click();
  await page.getByLabel("Notes for Steering play").fill("Play at the rack, check tie rods");
  await page.getByLabel("Notes for Steering play").blur();
  await page.getByRole("button", { name: "Submit inspection" }).click();
  await expect(page.getByText("Submitted", { exact: true }).first()).toBeVisible();

  // Back on the job card: inspection listed, assign a mechanic.
  await page.goto(jobUrl);
  await expect(page.getByText("1 failed")).toBeVisible();
  await page.getByRole("button", { name: "Assign mechanic" }).click();
  const select = page.getByLabel("Mechanic");
  await expect(select.locator("option").nth(1)).toBeAttached();
  await select.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Assign", exact: true }).click();
  await expect(page.getByRole("button", { name: "Unassign" })).toBeVisible();

  // Workflow and approval rule.
  await page.getByRole("button", { name: "Start diagnosis" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Start diagnosis" }).click();
  await expect(page.getByRole("button", { name: "Start repair" })).toBeDisabled();
});

test("book an appointment and check the customer in", async ({ page }, testInfo) => {
  const run = `${testInfo.project.name.slice(0, 1).toUpperCase()}${Date.now() % 100000}`;
  await signIn(page);
  await page.goto("/customers/new");
  await page.getByLabel("Surname").fill(`Booking${run}`);
  await page.getByRole("button", { name: "Register customer" }).click();
  await page.getByRole("link", { name: "Add vehicle" }).click();
  await page.getByLabel("Registration number").fill(`N ${run} B`);
  await page.getByLabel("Make").fill("Nissan");
  await page.getByLabel("Model", { exact: true }).fill("NP200");
  await page.getByRole("button", { name: "Register vehicle" }).click();
  await expect(page.getByRole("heading", { name: `N ${run} B` })).toBeVisible();

  await page.goto("/appointments/new");
  await page.getByLabel("Customer").fill(`Booking${run}`);
  await page.getByRole("button", { name: new RegExp(`Booking${run}`) }).click();
  await expect(page.getByLabel("Vehicle")).toHaveValue(/.+/);
  await page.getByLabel("Start").fill("14:30");
  await page.getByLabel("Reason for visit").fill("Clutch slipping");
  await page.getByRole("button", { name: "Book appointment" }).click();
  await expect(page).toHaveURL(/\/appointments\?/);
  const card = page.locator("article", { hasText: `Booking${run}` }).filter({ visible: true }).first();
  await expect(card.getByText("14:30–15:30")).toBeVisible();
  await card.getByRole("button", { name: "Check in" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Open job card" }).click();
  await expect(page.getByRole("heading", { name: /^JC-\d+$/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Customer complaint" }).or(page.locator("section", { hasText: "Customer complaint" })).getByText("Clutch slipping").first()).toBeVisible();
});
