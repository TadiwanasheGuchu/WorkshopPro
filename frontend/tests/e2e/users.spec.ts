import { expect, test, type Page } from "@playwright/test";

const OWNER_EMAIL = process.env.E2E_OWNER_EMAIL ?? "";
const OWNER_PASSWORD = process.env.E2E_OWNER_PASSWORD ?? "";
const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

test.skip(!OWNER_EMAIL || !OWNER_PASSWORD, "Set E2E_OWNER_EMAIL and E2E_OWNER_PASSWORD");

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

/** The status badge in the page header (field labels can share the same word). */
function statusBadge(page: Page, text: string) {
  return page.locator("span", { hasText: new RegExp(`^${text}$`) });
}

async function openNav(page: Page) {
  const menu = page.getByRole("button", { name: "Open navigation" });
  if (await menu.isVisible()) await menu.click();
}

async function invitationLink(request: import("@playwright/test").APIRequestContext, to: string): Promise<string> {
  for (let attempt = 0; attempt < 20; attempt++) {
    const list = await (await request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${to}`)}`)).json();
    const id = list.messages?.[0]?.ID;
    if (id) {
      const message = await (await request.get(`${MAILPIT}/api/v1/message/${id}`)).json();
      const match = /(https?:\/\/\S+\/accept-invitation#token=[\w-]+)/.exec(message.Text as string);
      if (match) return new URL(match[1]).pathname + new URL(match[1]).hash;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`No invitation email for ${to}`);
}

test("owner invites a mechanic who activates, signs in with limited access, and is deactivated", async ({
  browser,
  page,
  request,
}, testInfo) => {
  const email = `mech-${testInfo.project.name}-${Date.now()}@example.com`;
  const password = "spanner-and-socket-set";

  // Owner invites a mechanic for the main branch.
  await signIn(page, OWNER_EMAIL, OWNER_PASSWORD);
  await page.goto("/users/new");
  await page.getByLabel("Full name").fill("Petrus Mechanic");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByText(`Invitation sent to ${email}`)).toBeVisible();
  await expect(statusBadge(page, "Invited")).toBeVisible();
  const userUrl = page.url().split("?")[0];

  // Mechanic accepts the invitation from the email link.
  const mechanic = await browser.newPage();
  await mechanic.goto(await invitationLink(request, email));
  await expect(mechanic.getByText("Welcome, Petrus Mechanic")).toBeVisible();
  await mechanic.getByLabel("New password").fill(password);
  await mechanic.getByLabel("Repeat password").fill(password);
  await mechanic.getByRole("button", { name: "Activate account" }).click();
  await expect(mechanic.getByText("Your account is ready")).toBeVisible();

  // Mechanic signs in and sees no administration items they cannot use.
  await signIn(mechanic, email, password);
  await openNav(mechanic);
  await expect(mechanic.getByRole("link", { name: "Branches" }).first()).toBeVisible();
  await expect(mechanic.getByRole("link", { name: "Users & roles" })).toHaveCount(0);
  await expect(mechanic.getByRole("link", { name: "Audit log" })).toHaveCount(0);
  await mechanic.goto("/users");
  await expect(mechanic.getByText("You do not have access to this page")).toBeVisible();

  // Owner deactivates the mechanic; the mechanic's session ends immediately.
  await page.goto(userUrl);
  await expect(statusBadge(page, "Active")).toBeVisible();
  await page.getByRole("button", { name: "Deactivate user" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Deactivate" }).click();
  await expect(statusBadge(page, "Deactivated")).toBeVisible();

  await mechanic.goto("/");
  await expect(mechanic).toHaveURL(/\/sign-in/);
});

test("wrong password shows a single generic error", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill(OWNER_EMAIL);
  await page.getByLabel("Password").fill("definitely-wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "incorrect" })).toHaveText(
    "Email or password is incorrect.",
  );
});
