import { expect, test, type Page } from "@playwright/test";

/**
 * Browser acceptance of the scripted cases (PRD section 4.3: "10 of 10 scripted cases").
 * T01-T10 mirror backend/seed_data/scenarios.json; T21-T24 cover the paste-email, plain-form,
 * repeat-decision and dashboard flows. The backend starts from a freshly seeded synthetic database.
 * The cause pickers use the draft taxonomy "Category › Cause" labels.
 */

const SEARCH = /Customer number, order, container, name or postcode/;

async function openApp(page: Page, user = "demo.emp.a1") {
  await page.addInitScript(([u]) => { localStorage.setItem("cra.lang", "en"); localStorage.setItem("cra.user", u); sessionStorage.clear(); }, [user]);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Complaint Registration Assistant" })).toBeVisible();
}

async function search(page: Page, q: string) {
  await page.getByLabel(SEARCH).fill(q);
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

async function selectFirst(page: Page) {
  await page.getByRole("button", { name: /^(Select|Use this customer)$/ }).first().click();
  await expect(page.getByText("Customer context")).toBeVisible();
}

async function describe(page: Page, text: string, lang: "en" | "nl") {
  await page.getByRole("button", { name: "Next", exact: true }).click();               // review -> describe
  await page.getByLabel("Complaint description").fill(text);
  await page.getByLabel("Text language").selectOption(lang);
  await page.getByRole("button", { name: "Analyse and continue", exact: true }).click(); // one AI call
}

const next = (page: Page) => page.getByRole("button", { name: "Next", exact: true }).click();
const save = (page: Page) => page.getByRole("button", { name: "Save complaint", exact: true });
const saved = (page: Page) => expect(page.getByRole("status")).toContainText(/Saved as COM-\d+ \(PoC database only\)/);

test("T01 customer number, English text, suggested cause preselected, saved", async ({ page }) => {
  await openApp(page);
  await search(page, "100009");
  await expect(page.getByText(/100009/).first()).toBeVisible();
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption("C009-S1");
  await expect(page.locator(".row", { hasText: "Container" })).toBeVisible();
  await describe(page, "The container at our depot was not emptied on Tuesday, it was missed again.", "en");
  await expect(page.getByRole("heading", { name: /Summary/ })).toBeVisible();
  await expect(page.getByRole("radio", { name: /Missed collection/ }).first()).toBeChecked();   // confirm, don't type
  await expect(page.getByText("This cause list is a draft: 0 of 3 process owners have agreed so far.")).toBeVisible();
  await expect(page.getByLabel("Complaint type").first()).toHaveValue("service");
  await next(page);
  await expect(page.getByText("No repeat found under the current rule.")).toBeVisible();   // repeat result and Save share one screen
  await expect(save(page)).toBeVisible();
  await expect(page.getByText("5. Repeat check and save")).toBeVisible();                   // five steps, as in the PRD
  await expect(page.getByText(/^6\. /)).toHaveCount(0);
  await save(page).click();
  await saved(page);
});

test("T02 order number prefills site, order and container", async ({ page }) => {
  await openApp(page);
  await search(page, "ORD-002-10");
  await expect(page.getByText(/Matched via order/)).toBeVisible();
  await selectFirst(page);
  await expect(page.getByLabel("Site", { exact: true })).toHaveValue("C002-S1");
  await expect(page.getByLabel("Order", { exact: true })).toHaveValue("C002-O10");
  await expect(page.locator(".row", { hasText: "Container" }).getByText("BOX-002-1", { exact: true })).toBeVisible();
});

test("T03 container number finds the customer and site", async ({ page }) => {
  await openApp(page);
  await search(page, "BOX-004-2");
  await expect(page.getByText(/Matched via container/)).toBeVisible();
  await selectFirst(page);
  await expect(page.getByLabel("Site", { exact: true })).toHaveValue("C004-S2");
});

test("T04 ambiguous name: nothing is chosen automatically", async ({ page }) => {
  await openApp(page);
  await search(page, "Delta Works");
  await expect(page.getByText(/2 customers match/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Select", exact: true })).toHaveCount(2);
  await expect(page.getByText("Customer context")).toHaveCount(0);
});

test("T05 no match, then postcode search finds the customer", async ({ page }) => {
  await openApp(page);
  await search(page, "999999");
  await expect(page.getByText(/No customer found/)).toBeVisible();
  await search(page, "1009 ZZ");
  await expect(page.getByText(/Matched via postcode/)).toBeVisible();
  await expect(page.getByText(/100009/).first()).toBeVisible();
});

test("T06 Dutch complaint is accepted and summarised in Dutch", async ({ page }) => {
  await openApp(page);
  await search(page, "100009");
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption("C009-S1");
  await describe(page, "Onze container is vandaag niet geleegd, de inzameling is gemist.", "nl");
  await expect(page.getByLabel("What")).toHaveValue(/niet geleegd/);
  await expect(page.getByRole("radio", { name: /Missed collection/ }).first()).toBeChecked();
});

test("T07 invoice complaint switches type and applies that type's defaults", async ({ page }) => {
  await openApp(page);
  await search(page, "100018");
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption({ index: 1 });
  await describe(page, "We were charged twice on the latest invoice 20431, about €85,00.", "en");
  await expect(page.getByLabel("Complaint type").first()).toHaveValue("billing");
  await expect(page.getByLabel("Invoice no.")).toHaveValue("20431");               // template follows the type
  await page.getByRole("button", { name: "Back", exact: true }).click();                // classify -> describe
  await page.getByRole("button", { name: "Back", exact: true }).click();                // describe -> review
  await expect(page.getByLabel("Channel")).toHaveValue("phone");                  // how it arrived (search = on the phone), not the type
  await expect(page.getByLabel("Owner team")).toHaveValue("customer_service");
});

test("T08 low confidence: nothing preselected, save blocked until a cause is chosen", async ({ page }) => {
  await openApp(page);
  await search(page, "100019");
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption({ index: 1 });
  await describe(page, "Something odd happened but I am not sure what.", "en");
  await expect(page.getByText(/Low confidence/)).toBeVisible();
  await expect(page.getByRole("radio", { checked: true })).toHaveCount(0);
  await next(page);
  await expect(save(page)).toBeDisabled();
});

test("T09 'Other' needs a reason before leaving Classify", async ({ page }) => {
  await openApp(page);
  await search(page, "100020");
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption({ index: 1 });
  await describe(page, "A seagull built a nest under the lid of our container.", "en");
  await page.getByRole("radio", { name: /^Other$/ }).check();
  await expect(page.getByLabel(/Reason for 'Other'/)).toBeVisible();
  await page.getByLabel("Complaint type").first().selectOption("service");               // Other has no type of its own
  await expect(page.getByRole("alert").filter({ hasText: "Enter a reason for 'Other'" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeDisabled();   // blocked on Classify itself
  await page.getByLabel(/Reason for 'Other'/).fill("Seagull nest (synthetic)");
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeEnabled();
  await page.getByLabel(/Reason for 'Other'/).fill("   ");                                 // blanks do not count
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeDisabled();
  await page.getByLabel(/Reason for 'Other'/).fill(".");                                   // nor does a single character or punctuation
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeDisabled();
  await page.getByLabel(/Reason for 'Other'/).fill("ok");
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeDisabled();       // at least 3 characters
  await expect(page.getByRole("alert").filter({ hasText: "at least 3 characters" })).toBeVisible();
  await page.getByLabel(/Reason for 'Other'/).fill("Seagull nest (synthetic)");
  await next(page);
  await expect(save(page)).toBeEnabled();
  await save(page).click();
  await saved(page);
});

test("T10 seeded repeat is flagged with evidence; the dispute is stored next to the rule result", async ({ page, request }) => {
  await openApp(page);
  await search(page, "100001");
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption("C001-S1");
  await describe(page, "Container missed again.", "en");
  await expect(page.getByRole("radio", { name: /Missed collection/ }).first()).toBeChecked();
  await next(page);
  await expect(page.getByText(/Repeat complaint: 1 earlier matching complaint/)).toBeVisible();
  await expect(page.getByText(/COM-SEED-1/)).toBeVisible();
  await expect(page.getByText("Rule draft-juul-v1: same customer, same site, same cause category, within 60 days. Provisional: to be confirmed by Juul (Renewi).")).toBeVisible();
  await page.getByRole("radio", { name: "Not a repeat" }).check();
  await page.getByLabel("Reason (required)").fill("Different container this time");
  await save(page).click();
  await saved(page);
  const disputes = await (await request.get("http://127.0.0.1:8010/api/repeat-disputes", { headers: { "X-Demo-User": "demo.emp.a1" } })).json();
  expect(disputes.items[0]).toMatchObject({ prior_complaint_id: "COM-SEED-1", decision: "reject" });
  expect(disputes.items[0].evidence.is_repeat).toBe(true);                         // original rule result kept
});

test("T21 pasted email identifies the customer and fills the description", async ({ page }) => {
  await openApp(page);
  await page.getByText("Start from an email").click();
  await page.getByLabel("Pasted email").fill(
    "Van: planning@example.nl\nOnderwerp: Klacht\n\nGoedemorgen, onze container BOX-009-1 is vandaag niet geleegd. Klantnummer 100009.");
  await page.getByRole("button", { name: "Extract from email" }).click();
  await expect(page.getByText(/Customer identified via 100009/)).toBeVisible();
  await expect(page.getByText(/Matched via customer number/)).toBeVisible();
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption("C009-S1");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByLabel("Complaint description")).toHaveValue(/niet geleegd/);
  await expect(page.getByLabel("Complaint description")).not.toHaveValue(/Onderwerp/);
});

test("T23 dashboard (team lead) shows the success criteria, the step times and the exports", async ({ page }) => {
  await openApp(page, "demo.lead");
  await page.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByRole("heading", { name: "Success criteria" })).toBeVisible();
  await expect(page.getByText(/< 10% 'Other'/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Export CSV" })).toBeVisible();
  await expect(page.getByText(/\(median [\d.]+s, n = \d+\)/).first()).toBeVisible();                  // step card: mean and median
  await expect(page.getByText("Each visit to a step counts at most 10 minutes, so a tab left open is not counted. Going back and forth adds the visits up.")).toBeVisible();
});

test("T24 interface switches to Dutch", async ({ page }) => {
  await openApp(page);
  await page.getByLabel("Language").selectOption("nl");
  await expect(page.getByText("Klantnummer, order, container, naam of postcode")).toBeVisible();
  await expect(page.getByRole("button", { name: "Zoeken" })).toBeVisible();
});


// ---- Employee accounts: registration with a function category, approval, sign-in, role-based menu ----

const API = "http://127.0.0.1:8010";
const ADMIN = { "X-Demo-User": "demo.admin" };

async function openSignedOut(page: Page) {
  await page.addInitScript(() => { localStorage.setItem("cra.lang", "en"); localStorage.removeItem("cra.user"); sessionStorage.clear(); });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Complaint Registration Assistant" })).toBeVisible();
}

test("T25 employee creates an account with a function, an admin approves it, then they sign in", async ({ page, request }) => {
  await openSignedOut(page);
  await expect(page.getByLabel("Work e-mail address")).toBeVisible();                       // sign-in screen first
  await page.getByRole("tab", { name: "Create account" }).click();
  await expect(page.getByRole("radio", { name: "Customer service" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Sales" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Site operations" })).toBeVisible();
  await page.getByLabel("Full name").fill("Sanne de Vries");
  await page.getByLabel("Work e-mail address").fill("sanne.devries@example.nl");
  await page.getByLabel("Password", { exact: true }).fill("correct-horse-9");
  await page.getByLabel("Repeat password").fill("correct-horse-9");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert")).toContainText("Choose the team you register complaints for.");   // function is required
  await page.getByRole("radio", { name: "Sales" }).check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("An administrator must approve it before you can sign in.")).toBeVisible();

  await page.getByLabel("Work e-mail address").fill("sanne.devries@example.nl");          // not approved yet
  await page.getByLabel("Password", { exact: true }).fill("correct-horse-9");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Your account is waiting for approval by an administrator.")).toBeVisible();

  const pending = await (await request.get(`${API}/api/users`, { headers: ADMIN, params: { status: "pending" } })).json();
  const me = pending.items.find((u: any) => u.email === "sanne.devries@example.nl");
  expect(me).toMatchObject({ function: "sales", role: "employee" });
  expect((await request.patch(`${API}/api/users/${me.id}`, { headers: ADMIN, data: { status: "active" } })).ok()).toBe(true);

  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Sanne de Vries")).toBeVisible();
  await expect(page.getByText("Sales · employee")).toBeVisible();
  await expect(page.getByLabel("Customer number, order, container, name or postcode")).toBeVisible();   // lands on Register
  const menu = page.getByRole("navigation", { name: "Main navigation" });
  await expect(menu.getByRole("button", { name: "Register" })).toBeVisible();
  await expect(menu.getByRole("button", { name: "History" })).toBeVisible();
  await expect(menu.getByRole("button", { name: "Dashboard" })).toHaveCount(0);            // not for employees
  await expect(menu.getByRole("button", { name: "Configuration" })).toHaveCount(0);
  await expect(menu.getByRole("button", { name: "Users" })).toHaveCount(0);

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Work e-mail address")).toBeVisible();
});

test("T26 wrong password gives a generic message; the form validates the sign-up", async ({ page }) => {
  await openSignedOut(page);
  await page.getByLabel("Work e-mail address").fill("nobody@example.nl");
  await page.getByLabel("Password", { exact: true }).fill("not-a-real-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Incorrect e-mail address or password.");
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.getByLabel("Full name").fill("Test Person");
  await page.getByLabel("Work e-mail address").fill("test.person@example.nl");
  await page.getByLabel("Password", { exact: true }).fill("long-enough-pw-1");
  await page.getByLabel("Repeat password").fill("something-else-123");
  await page.getByRole("radio", { name: "Site operations" }).check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert")).toContainText("The passwords do not match.");
});

test("T27 admin approves a new employee on the Users screen; roles land on their own first screen", async ({ page, request }) => {
  await request.post(`${API}/api/auth/register`, { data: { name: "Joost Bakker", email: "joost.bakker@example.nl", password: "another-long-pw-1", function: "customer_service" } });
  await openApp(page, "demo.admin");
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();                // admin lands on Users
  await expect(page.getByText("Joost Bakker").first()).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).first().click();
  await expect(page.getByText("No accounts are waiting for approval.")).toBeVisible();
  await openApp(page, "demo.lead");
  await expect(page.getByRole("heading", { name: "Success criteria" })).toBeVisible();          // team lead lands on the dashboard
});

// ---- Find customer, in detail ----

test("T28 one match is shown at once with how it was found; one click continues", async ({ page }) => {
  await openApp(page);
  await search(page, "ORD-002-10");
  await expect(page.getByText("Customer found")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Delta Works Logistiek BV" })).toBeVisible();
  await expect(page.getByText(/Matched via order number · order ORD-002-10/)).toBeVisible();
  await expect(page.getByText(/Last order 2026-10-27/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Select", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Use this customer" })).toBeFocused();       // Enter continues
  await page.keyboard.press("Enter");
  await expect(page.getByText("Customer context")).toBeVisible();
});

test("T29 several matches are listed and nothing is chosen; no match explains what to try", async ({ page }) => {
  await openApp(page);
  await search(page, "Delta Works");
  await expect(page.getByText(/2 customers match “Delta Works”\. Choose the right one/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Select", exact: true })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Use this customer" })).toHaveCount(0);
  await expect(page.getByText("Customer context")).toHaveCount(0);
  await search(page, "ZZZ-nothing");
  await expect(page.getByText("No customer found for “ZZZ-nothing”.")).toBeVisible();
  await expect(page.getByText(/container number, starting with BOX-/)).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByLabel(SEARCH)).toHaveValue("");
});

test("T30 the search box says what kind of identifier it looks like", async ({ page }) => {
  await openApp(page);
  await page.getByLabel(SEARCH).fill("BOX-004-2");
  await expect(page.getByText("Looks like a container number")).toBeVisible();
  await page.getByLabel(SEARCH).fill("100009");
  await expect(page.getByText("Looks like a customer number")).toBeVisible();
  await page.getByLabel(SEARCH).fill("1009 ZZ");
  await expect(page.getByText("Looks like a postcode")).toBeVisible();
});

test("T21b the email panel reports language, identifiers and the copied complaint text", async ({ page }) => {
  await openApp(page);
  await page.getByText("Start from an email").click();
  await page.getByLabel("Pasted email").fill("Subject: Klacht\n\nOnze container BOX-009-1 is niet geleegd. Klantnummer 100009.");
  await page.getByRole("button", { name: "Extract from email" }).click();
  await expect(page.getByText(/Found in the email: .*100009 ✓/)).toBeVisible();
  await expect(page.getByText(/Language: NL/)).toBeVisible();
  await expect(page.getByText(/The complaint text was copied to the next step/)).toBeVisible();
  await expect(page.getByText("Customer found")).toBeVisible();
});

test("T31 a real administrator (own password, no demo account) approves people and creates accounts with temporary passwords", async ({ page, request }) => {
  await request.post(`${API}/api/auth/register`, { data: { name: "Lotte Meijer", email: "lotte.meijer@example.nl", password: "lotte-long-pw-1", function: "sales" } });
  await openSignedOut(page);
  await page.getByLabel("Work e-mail address").fill("admin@example.nl");
  await page.getByLabel("Password", { exact: true }).fill("e2e-admin-password-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Users", exact: true })).toBeVisible();     // admin lands on Users
  await expect(page.getByText("Test Admin").first()).toBeVisible();

  const waiting = page.getByRole("heading", { name: /Waiting for approval/ }).locator("xpath=..");
  await waiting.getByRole("row", { name: /Lotte Meijer/ }).getByRole("button", { name: "Approve" }).click();
  await expect(waiting.getByText("Lotte Meijer")).toHaveCount(0);

  const form = page.locator("form", { hasText: "Add a person" });
  await form.getByLabel("Full name").fill("Pieter Smit");
  await form.getByLabel("E-mail").fill("pieter.smit@example.nl");
  await form.getByLabel("Function").selectOption("site_operations");
  await form.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Temporary password for Pieter Smit")).toBeVisible();
  const temp = (await page.locator("code").innerText()).trim();
  expect(temp.length).toBeGreaterThanOrEqual(12);
  await page.getByRole("button", { name: "I have noted it" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();

  // The new person signs in with the temporary password and must choose their own before anything else.
  await page.getByLabel("Work e-mail address").fill("pieter.smit@example.nl");
  await page.getByLabel("Password", { exact: true }).fill(temp);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await expect(page.getByLabel("Customer number, order, container, name or postcode")).toHaveCount(0);
  await page.getByLabel("Current password").fill(temp);
  await page.getByLabel("New password", { exact: true }).fill("pieter-own-password-1");
  await page.getByLabel("Repeat new password").fill("pieter-own-password-1");
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page.getByLabel("Customer number, order, container, name or postcode")).toBeVisible();   // now in the app
  await expect(page.getByText("Site operations · employee")).toBeVisible();
  await expect(page.getByRole("button", { name: "Change password" })).toBeVisible();

  // Lotte (approved above) can sign in with her own password.
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByLabel("Work e-mail address").fill("lotte.meijer@example.nl");
  await page.getByLabel("Password", { exact: true }).fill("lotte-long-pw-1");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Sales · employee")).toBeVisible();
});

test("T32 customer data is three tabbed tables; a row's Use button fills the form", async ({ page }) => {
  await openApp(page);
  await search(page, "100009");
  await selectFirst(page);
  const data = page.getByRole("region", { name: "Customer context" });
  await expect(data.getByRole("tab", { name: "Sites (2)" })).toBeVisible();
  await expect(data.getByRole("tab", { name: /Active contracts \(\d+\)/ })).toBeVisible();       // the chosen site's contracts: the site is prefilled
  await expect(data.getByRole("tab", { name: /orders \(\d+\)/i })).toBeVisible();

  await data.getByRole("tab", { name: /Sites/ }).click();
  await expect(data.getByText("Postcode", { exact: true })).toBeVisible();
  await data.getByRole("row", { name: /Synthetic depot 2/ }).getByRole("button", { name: "Use" }).click();
  await expect(page.getByLabel("Site", { exact: true })).toHaveValue("C009-S2");
  await expect(data.getByRole("row", { name: /Synthetic depot 2/ }).getByText("Selected")).toBeVisible();

  await data.getByRole("tab", { name: /orders/i }).click();
  await expect(data.getByText("Showing Synthetic depot 2 only.")).toBeVisible();          // orders follow the chosen site
  const rows = data.getByRole("row").filter({ hasText: "BOX-009-2" });
  await expect(rows.first()).toBeVisible();
  await expect(data.getByRole("row").filter({ hasText: "BOX-009-1" })).toHaveCount(0);
  await rows.nth(1).getByRole("button", { name: "Use" }).click();
  await expect(page.locator(".row", { hasText: "Container" }).getByText("BOX-009-2")).toBeVisible();
  await data.getByRole("button", { name: "Show all sites" }).click();
  await expect(data.getByRole("row").filter({ hasText: "BOX-009-1" }).first()).toBeVisible();

  await data.getByRole("tab", { name: /contracts/i }).click();
  await expect(data.getByText("CON-009-1").first()).toBeVisible();
  await expect(data.getByRole("row", { name: /CON-009-2/ }).getByText("Selected")).toBeVisible();   // prefilled by choosing the site
  await data.getByRole("row", { name: /CON-009-1/ }).getByRole("button", { name: "Use" }).click();
  await expect(page.getByLabel("Contract", { exact: true })).toHaveValue("C009-K1");
  await expect(page.getByLabel("Site", { exact: true })).toHaveValue("C009-S1");              // the contract's site came with it
});

test("T33 an employee adds a site, container, contract and order; they appear in the registration dropdowns", async ({ page }) => {
  await openApp(page);
  await search(page, "100009");
  await selectFirst(page);
  await expect(page.locator(".row", { hasText: "Registered by" })).toContainText("Demo Employee A1");   // a name, not an id
  await expect(page.getByRole("button", { name: /Add or manage this customer's sites/ })).toHaveCount(0);   // reached through the menu instead
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Sites", exact: true }).click();

  const left = page.getByRole("navigation", { name: "Main navigation" });
  await expect(page.getByRole("heading", { name: "Sites", exact: true })).toBeVisible();          // Sites is a menu item of its own
  await expect(page.getByText("1–2 of 2")).toBeVisible();                                           // the customer carried over (2 sites)

  await page.getByRole("button", { name: "Add a site" }).click();
  const site = page.getByRole("form", { name: "Add a site" });
  await site.getByLabel("Name").fill("Synthetic depot 3");
  await site.getByLabel("Postcode").fill("1009 ZZ");
  await site.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Added. It now appears in the registration dropdowns.")).toBeVisible();
  await expect(page.getByRole("row", { name: /Synthetic depot 3/ }).getByText("Added in the PoC")).toBeVisible();
  await expect(page.getByText("1–3 of 3")).toBeVisible();

  await left.getByRole("button", { name: "Containers", exact: true }).click();
  await page.getByRole("button", { name: "Add a container" }).click();
  const box = page.getByRole("form", { name: "Add a container" });
  await box.getByLabel("Site").selectOption({ label: "Synthetic depot 3 (SITE-009-3)" });
  await box.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("row", { name: /BOX-009-3/ }).getByText("Added in the PoC")).toBeVisible();   // number generated

  await left.getByRole("button", { name: "Contracts", exact: true }).click();
  await page.getByRole("button", { name: "Add a contract" }).click();
  const contract = page.getByRole("form", { name: "Add a contract" });
  await contract.getByLabel("Site").selectOption({ label: "Synthetic depot 3 (SITE-009-3)" });
  await contract.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("row", { name: /CON-009-3/ })).toBeVisible();

  await left.getByRole("button", { name: "Orders", exact: true }).click();
  await page.getByRole("button", { name: "Add an order" }).click();
  const order = page.getByRole("form", { name: "Add an order" });
  await order.getByLabel("Site").selectOption({ label: "Synthetic depot 3 (SITE-009-3)" });
  await order.getByLabel("Container").selectOption("BOX-009-3");
  await order.getByLabel("Contract").selectOption({ label: "CON-009-3" });
  await order.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("row", { name: /ORD-009-P1/ }).getByText("Added in the PoC")).toBeVisible();

  await page.getByRole("button", { name: "Back to the complaint" }).click();                       // registration is where it was
  await expect(page.getByText("Customer context")).toBeVisible();
  const siteSelect = page.getByLabel("Site", { exact: true });
  await expect(siteSelect.locator("option", { hasText: "Synthetic depot 3" })).toHaveCount(1);       // new site is in the dropdown
  await siteSelect.selectOption("C009-S3");
  await expect(page.getByLabel("Contract", { exact: true })).toHaveValue("C009-K3");               // and its contract, order, container
  await expect(page.getByLabel("Order", { exact: true })).toHaveValue("C009-OP1");
  await expect(page.locator(".row", { hasText: "Container" }).getByText("BOX-009-3")).toBeVisible();
});

test("T34 roles without the permission do not see Customer data", async ({ page }) => {
  const menu = page.getByRole("navigation", { name: "Main navigation" });
  await openApp(page, "demo.lead");
  await expect(menu.getByRole("button", { name: "Sites", exact: true })).toHaveCount(0);
  await expect(menu.getByText("Customer data")).toHaveCount(0);
  await openApp(page, "demo.emp.a1");
  await expect(menu.getByText("Customer data")).toBeVisible();                                        // the group heading
  for (const item of ["Customers", "Sites", "Contracts", "Orders", "Containers"]) await expect(menu.getByRole("button", { name: item, exact: true })).toBeVisible();
});

test("T35 Customers page lists every customer; an employee adds a customer and registers for it", async ({ page }) => {
  await openApp(page);
  const menu = page.getByRole("navigation", { name: "Main navigation" });
  await menu.getByRole("button", { name: "Customers", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customers", exact: true })).toBeVisible();
  await expect(page.getByText("1–25 of 34")).toBeVisible();                                         // all customers, paged
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("26–34 of 34")).toBeVisible();
  await page.getByLabel("Search").fill("delta works");
  await expect(page.getByText("1–2 of 2")).toBeVisible();
  await expect(page.getByRole("row", { name: /Delta Works/ })).toHaveCount(2);
  await page.getByLabel("Search").fill("");

  await page.getByRole("button", { name: "Add a customer" }).click();
  const form = page.getByRole("form", { name: "Add a customer" });
  await form.getByLabel("Name").fill("Nieuwe Klant BV");
  await form.getByLabel("Postcode").fill("3511 AB");
  await form.getByLabel("First site (optional)").fill("Hoofdlocatie");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Customer added: Nieuwe Klant BV (100035).")).toBeVisible();
  await page.getByLabel("Search").fill("nieuwe klant");
  const row = page.getByRole("row", { name: /Nieuwe Klant BV/ });
  await expect(row.getByText("Added in the PoC")).toBeVisible();
  await row.getByRole("button", { name: "Open" }).click();                                          // goes to that customer's sites
  await expect(page.getByRole("heading", { name: "Sites", exact: true })).toBeVisible();
  await expect(page.getByRole("row", { name: /Hoofdlocatie/ })).toBeVisible();
  await expect(page.getByText("1–1 of 1")).toBeVisible();

  await menu.getByRole("button", { name: "Register", exact: true }).click();                        // the new customer works in the registration
  await search(page, "100035");
  await expect(page.getByRole("heading", { name: "Nieuwe Klant BV" })).toBeVisible();
  await selectFirst(page);
  await expect(page.getByLabel("Site", { exact: true }).locator("option", { hasText: "Hoofdlocatie" })).toHaveCount(1);
});

test("T36 data pages list all customers with a customer column; adding there asks for the customer", async ({ page }) => {
  await openApp(page);
  const menu = page.getByRole("navigation", { name: "Main navigation" });
  await menu.getByRole("button", { name: "Sites", exact: true }).click();
  const filter = page.locator(".customer-bar select");
  await expect(filter).toHaveValue("");                                                              // no customer chosen: all of them
  await expect(page.locator("th", { hasText: "Customer" }).first()).toBeVisible();                   // the customer column
  await expect(page.getByText(/1–25 of \d+/)).toBeVisible();                                           // many sites, paged
  const customerCells = await page.locator("table.data-table tbody tr td:first-child").allInnerTexts();
  expect(new Set(customerCells).size).toBeGreaterThan(5);                                           // rows of many different customers
  await page.getByLabel("Search").fill("site-009");
  await expect(page.getByText(/1–\d+ of \d+/)).toBeVisible();
  await expect(page.getByRole("row", { name: /SITE-009-1/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /SITE-001-1/ })).toHaveCount(0);                        // the search narrows the list
  await page.getByLabel("Search").fill("");

  await page.getByRole("button", { name: "Add a site" }).click();
  const form = page.getByRole("form", { name: "Add a site" });
  await form.getByLabel(/^Customer/).selectOption({ label: "Zorgcentrum Het Anker · 100009" });
  await form.getByLabel("Name").fill("Synthetic depot 9");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Added. It now appears in the registration dropdowns.")).toBeVisible();
  await page.getByLabel("Search").fill("depot 9");
  await expect(page.getByRole("row", { name: /Zorgcentrum Het Anker.*Synthetic depot 9/ })).toBeVisible();

  await menu.getByRole("button", { name: "Orders", exact: true }).click();                          // newest orders first, across customers
  await expect(page.getByText(/1–25 of \d+/)).toBeVisible();
  await filter.selectOption({ label: "Zorgcentrum Het Anker · 100009" });
  await expect(page.getByText(/1–25 of \d+/)).toBeVisible();
  await expect(page.getByRole("row", { name: /Delta Works/ })).toHaveCount(0);                      // filtered to one customer
});

test("T37 the result card already shows the contract and the ten latest orders (step 1)", async ({ page }) => {
  await openApp(page);
  await search(page, "100009");
  const card = page.locator(".card.found");
  await expect(card.getByText("Customer found")).toBeVisible();
  await expect(card.getByText(/Contracts:/)).toBeVisible();
  await expect(card.getByText(/CON-009-1 \(Synthetic depot 1, valid to 2027-08-24\)/)).toBeVisible();
  await expect(card.getByText("Last 10 orders:")).toBeVisible();
  await expect(card.locator("li")).toHaveCount(10);                                           // the ten latest, all sites
  const items = await card.locator("li").allInnerTexts();
  expect(items.every((t) => /^ORD-009-\w+ · BOX-009-\d · \d{4}-\d{2}-\d{2} · \w+ · Synthetic depot \d$/.test(t))).toBe(true);   // reference · container · date · status · site
  const dates = items.map((t) => t.split(" · ")[2]);
  expect(dates).toEqual([...dates].sort().reverse());                                         // newest first
  await search(page, "ORD-002-10");                                                           // matched by an order: still the customer's last ten
  await expect(page.locator(".card.found").getByText(/Matched via order number/)).toBeVisible();
  await expect(page.locator(".card.found li")).toHaveCount(10);
  await expect(page.locator(".card.found li").filter({ hasText: "ORD-002-10" })).toHaveCount(1);
  await search(page, "100021");                                                               // seeded customer with an expired contract
  await expect(page.locator(".card.found").getByText("No active contract")).toBeVisible();
});

const field = (page: Page, label: string) => page.locator(".row", { hasText: label });

test("T38 phone path: channel, priority and status are already filled when Review details opens; the type completes the rest", async ({ page }) => {
  await openApp(page);
  await search(page, "100009");
  await selectFirst(page);
  await expect(page.getByLabel("Channel")).toHaveValue("phone");                                   // the customer is on the phone
  await expect(field(page, "Channel")).toContainText("Default");
  await expect(page.getByLabel("Priority")).toHaveValue("normal");
  await expect(field(page, "Priority")).toContainText("Default");
  await expect(page.getByLabel("Owner team")).toHaveValue("");                                      // genuinely depends on the type
  await expect(page.getByText("Choose the complaint type: it fills in the owner team and the response target.")).toBeVisible();
  const order = await page.locator(".row label").allInnerTexts();
  expect(order.indexOf("Complaint type")).toBeLessThan(order.indexOf("Site"));                      // the one field to choose comes first

  await page.getByLabel("Complaint type").selectOption("billing");                                  // choosing it completes the defaults
  await expect(page.getByLabel("Owner team")).toHaveValue("customer_service");
  await expect(field(page, "Owner team")).toContainText("Default");
  await expect(page.getByLabel("Channel")).toHaveValue("phone");                                    // the channel is about this call
  await expect(page.getByText("Choose the complaint type: it fills in the owner team and the response target.")).toHaveCount(0);
});

test("T39 email path: channel is email and the type is already suggested, so every default is filled", async ({ page }) => {
  await openApp(page);
  await page.getByText("Start from an email").click();
  await page.getByLabel("Pasted email").fill("Subject: Klacht\n\nOnze container BOX-009-1 is vandaag niet geleegd. Klantnummer 100009.");
  await page.getByRole("button", { name: "Extract from email" }).click();
  await expect(page.getByText("Customer found")).toBeVisible();
  await selectFirst(page);
  await expect(page.getByLabel("Channel")).toHaveValue("email");
  await expect(field(page, "Channel")).toContainText("Default");
  await expect(page.getByLabel("Complaint type")).toHaveValue("service");                           // guessed from the email text
  await expect(field(page, "Complaint type")).toContainText("Suggested");
  await expect(page.getByLabel("Owner team")).toHaveValue("operations");                            // the type's defaults came with it
  await expect(page.getByLabel("Priority")).toHaveValue("normal");
  await expect(page.getByText("Choose the complaint type: it fills in the owner team and the response target.")).toHaveCount(0);
});

test("T40 a type chosen earlier is kept together with its defaults when the customer is selected again", async ({ page }) => {
  await openApp(page);
  await search(page, "100009");
  await selectFirst(page);
  await page.getByLabel("Complaint type").selectOption("billing");
  await expect(page.getByLabel("Owner team")).toHaveValue("customer_service");
  await page.getByRole("button", { name: "Back", exact: true }).click();                           // back to Find customer
  await search(page, "100009");
  await selectFirst(page);
  await expect(page.getByLabel("Complaint type")).toHaveValue("billing");                           // not lost
  await expect(page.getByLabel("Owner team")).toHaveValue("customer_service");                      // never a default without its type
  await expect(page.getByText("Choose the complaint type: it fills in the owner team and the response target.")).toHaveCount(0);
});

test("T41 the header controls stay inside the window on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 800 });
  await openApp(page);
  const signOut = page.getByRole("button", { name: /Sign out|Exit demo/ });
  await expect(signOut).toBeVisible();
  const box = await signOut.boundingBox();
  expect(box!.x + box!.width).toBeLessThanOrEqual(1100);                                            // not pushed past the right edge
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);   // no sideways scrolling
});

test("T42 an order picked after the summary was made fills the empty container number", async ({ page }) => {
  await openApp(page);
  await search(page, "100012");
  await selectFirst(page);
  await page.getByLabel("Complaint type").selectOption("service");
  await expect(page.getByLabel("Owner team")).toHaveValue("operations");                           // let the type's update finish first
  await page.getByLabel("Order", { exact: true }).selectOption("");                                // the order was prefilled: clear it
  await describe(page, "De container is vandaag niet geleegd.", "nl");                              // no container in the text, no order chosen
  await expect(page.getByLabel("Container no.")).toHaveValue("");
  await page.getByRole("button", { name: "Back", exact: true }).click();                           // classify -> describe
  await page.getByRole("button", { name: "Back", exact: true }).click();                           // describe -> review
  const data = page.getByRole("region", { name: "Customer context" });
  await data.getByRole("tab", { name: /orders/i }).click();
  await data.getByRole("row").filter({ hasText: "BOX-012-1" }).first().getByRole("button", { name: "Use" }).click();
  await next(page);
  await next(page);                                                                                // same text: no new AI call
  await expect(page.getByLabel("Container no.")).toHaveValue("BOX-012-1");
  await expect(page.locator(".row", { hasText: "Container no." }).getByText("Prefilled")).toBeVisible();
});

test("T43 the admin must choose the team a lead leads", async ({ page }) => {
  await openApp(page, "demo.admin");
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
  const form = page.locator("form.card");
  const field = (name: string) => form.locator("label").filter({ hasText: new RegExp(`^${name}`) }).locator("select");
  await page.getByLabel("Full name").fill("Anna Lead");
  await page.getByLabel("E-mail", { exact: true }).fill("anna.lead@example.nl");
  await expect(form.locator("label").filter({ hasText: /^Function/ })).toBeVisible();                          // employees: a plain function
  await field("Role").selectOption("lead");
  await expect(form.locator("label").filter({ hasText: /^Team led/ })).toBeVisible();                          // leads: the team they lead
  await expect(page.getByRole("button", { name: "Create account" })).toBeDisabled();               // no team yet
  await field("Team led").selectOption({ label: "Sales" });
  await expect(page.getByRole("button", { name: "Create account" })).toBeEnabled();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Temporary password for Anna Lead")).toBeVisible();
  await expect(page.getByLabel("Team led Anna Lead")).toHaveValue("sales");                       // editable in the list
});

test("T44 a team lead sees one team: banner, no user-group split, suggestions export", async ({ page }) => {
  await openApp(page, "demo.lead");
  await page.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Team: Group a" })).toBeVisible();
  await expect(page.locator("article.card", { hasText: "By user group" })).toHaveCount(0);               // one team only: nothing to split
  await expect(page.getByRole("button", { name: /Export suggestions CSV/ })).toBeVisible();
  await openApp(page, "demo.admin");                                                              // admins are not limited
  await page.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByText(/^Team: /)).toHaveCount(0);
});

test("T45 the summary and the cause are recorded as accepted when left alone and as changed when edited", async ({ page, request }) => {
  const outcomes = async (id: string) => {
    const csv = await (await request.get(`${API}/api/export/suggestions.csv`, { headers: { "X-Demo-User": "demo.admin" } })).text();
    const rows = csv.trim().split(/\r?\n/).map((l) => l.split(","));
    return Object.fromEntries(rows.filter((r) => r[0] === id).map((r) => [r[6], r[8]]));
  };
  const run = async (edit: boolean) => {
    await openApp(page);
    await search(page, "100009");
    await selectFirst(page);
    await page.getByLabel("Site", { exact: true }).selectOption("C009-S1");
    await describe(page, "The container at our depot was not emptied on Tuesday, it was missed again.", "en");
    await expect(page.getByRole("radio", { name: /Missed collection/ }).first()).toBeChecked();
    if (edit) {
      await page.getByLabel("What", { exact: true }).fill("Edited by the employee");
      await page.getByRole("radio", { name: /Late collection/ }).first().check();
    }
    await next(page);
    await save(page).click();
    await saved(page);
    return (await page.getByRole("status").innerText()).match(/COM-\d+/)![0];
  };
  const kept = await outcomes(await run(false));
  expect(kept).toMatchObject({ summary: "accepted", root_cause: "accepted", description: "typed" });
  const changed = await outcomes(await run(true));
  expect(changed).toMatchObject({ summary: "changed", root_cause: "changed" });
});

test("T46 a real team lead signs in with their own password and sees only their team", async ({ page, request }) => {
  const create = async (name: string, email: string, fn: string, role: string) =>
    (await (await request.post(`${API}/api/users`, { headers: ADMIN, data: { name, email, function: fn, role } })).json()).temporary_password as string;
  const ownPassword = async (email: string, temp: string) => {                                    // first sign-in: choose a password
    const first = await (await request.post(`${API}/api/auth/login`, { data: { email, password: temp } })).json();
    const done = await (await request.post(`${API}/api/auth/change-password`, { headers: { Authorization: `Bearer ${first.token}` }, data: { current_password: temp, new_password: "own-password-12345" } })).json();
    return { Authorization: `Bearer ${done.token}` };
  };
  const sanne = await ownPassword("sanne.sales@example.nl", await create("Sanne Sales", "sanne.sales@example.nl", "sales", "employee"));
  const karel = await ownPassword("karel.klant@example.nl", await create("Karel Klant", "karel.klant@example.nl", "customer_service", "employee"));
  const leadTemp = await create("Lotte Lead", "lotte.lead@example.nl", "sales", "lead");
  for (const h of [sanne, karel]) expect((await request.post(`${API}/api/sessions`, { headers: h, data: {} })).ok()).toBe(true);

  await openSignedOut(page);                                                                     // the real sign-in screen
  await page.getByLabel("Work e-mail address").fill("lotte.lead@example.nl");
  await page.getByLabel("Password", { exact: true }).fill(leadTemp);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await page.getByLabel("Current password").fill(leadTemp);
  await page.getByLabel("New password", { exact: true }).fill("lotte-own-password-1");
  await page.getByLabel("Repeat new password").fill("lotte-own-password-1");
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();                  // a lead lands on the dashboard
  await expect(page.getByRole("status").filter({ hasText: "Team: Sales" })).toBeVisible();       // only the team they lead
  await expect(page.locator("article.card", { hasText: "By user group" })).toHaveCount(0);
  const menu = page.getByRole("navigation", { name: "Main navigation" });
  await expect(menu.getByRole("button", { name: "Register" })).toHaveCount(0);                   // leads do not register
  // The per-employee table, with real accounts and no demo header: the people of the lead's team only.
  const people = page.locator("article", { has: page.getByRole("heading", { name: "By employee" }) });
  await expect(people.getByRole("cell", { name: "Sanne Sales" })).toBeVisible();
  await expect(people.getByRole("cell", { name: "Karel Klant" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Export employees CSV" })).toBeVisible();
});

test("T47 the About page lists what is still to be agreed and who confirms it", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: "About" }).click();
  await expect(page.getByText("Five-step registration")).toBeVisible();                           // no longer six
  await expect(page.getByText("Still to be agreed")).toBeVisible();
  await expect(page.getByRole("row", { name: /repeat_rule\.lookback_days.*Juul \(Renewi\)/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /taxonomy.*Glenn \/ process owners/ })).toBeVisible();
});

test("T48 the registration clock starts at the first click or key, so finding the customer counts but waiting before it does not", async ({ page, request }) => {
  await openApp(page);
  await page.waitForTimeout(4000);                                                                // the screen sits open: not counted
  await page.getByLabel(SEARCH).click();                                                          // the employee begins
  await page.waitForTimeout(3000);                                                                // taking a moment to search: counted
  await search(page, "100009");
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption("C009-S1");
  await page.getByRole("button", { name: "Next", exact: true }).click();                           // review -> describe: a step event closes the first step
  const rows = await (await request.get(`${API}/api/analytics/sessions`, { headers: ADMIN, params: { page_size: 1 } })).json();
  const mine = rows.items[0];
  expect(mine.step_seconds.find_customer).toBeGreaterThanOrEqual(3);                              // not the ~1 s of the lookup call
  expect(mine.step_seconds.find_customer).toBeLessThan(7.5);                                      // and without the 4 s the screen sat open before the first click
  expect(mine.first_field_seconds).toBeGreaterThanOrEqual(3);                                      // lookup filled the first field after the search
  await openApp(page, "demo.admin");
  await page.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByText("First field filled (s)")).toBeVisible();
  await expect(page.getByText("First own entry (s)")).toBeVisible();
});

test("T49 a team lead sees how each person of their team registers; an admin also sees the team column", async ({ page }) => {
  await openApp(page, "demo.lead");
  await page.getByRole("button", { name: "Dashboard" }).click();
  const people = page.locator("article", { has: page.getByRole("heading", { name: "By employee" }) });
  await expect(people).toBeVisible();
  await expect(people.getByRole("cell", { name: "Whole team" })).toBeVisible();                  // the team as the first row, to compare with
  await expect(people.getByRole("cell", { name: "Demo Employee A1" })).toBeVisible();            // a person of the lead's own team
  await expect(people.getByRole("cell", { name: "Demo Employee B1" })).toHaveCount(0);           // never someone from another team
  await expect(people.locator("th", { hasText: /^Group$/ })).toHaveCount(0);                      // one team: no team column
  await expect(people.locator("th", { hasText: /^Employee$/ })).toBeVisible();                    // (so this check can fail)
  await expect(people.getByText(/Shares based on fewer than 3 registrations are hidden/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Export employees CSV" })).toBeVisible();

  await openApp(page, "demo.admin");
  await page.getByRole("button", { name: "Dashboard" }).click();
  const all = page.locator("article", { has: page.getByRole("heading", { name: "By employee" }) });
  await expect(all.locator("th", { hasText: /^Group$/ })).toBeVisible();                           // admins see every team
});

test("T50 the process owners agree the cause list: three real accounts, the last one on the page", async ({ page, request }) => {
  const create = async (name: string, email: string) =>
    (await (await request.post(`${API}/api/users`, { headers: ADMIN, data: { name, email, function: null, role: "evaluator" } })).json()).temporary_password as string;
  const ownPassword = async (email: string, temp: string) => {                                    // first sign-in: choose a password
    const first = await (await request.post(`${API}/api/auth/login`, { data: { email, password: temp } })).json();
    const done = await (await request.post(`${API}/api/auth/change-password`, { headers: { Authorization: `Bearer ${first.token}` }, data: { current_password: temp, new_password: "owner-password-1234" } })).json();
    return { Authorization: `Bearer ${done.token}` };
  };
  const kwafie = await ownPassword("kwafie.owner@example.nl", await create("Kwafie Owner", "kwafie.owner@example.nl"));
  const naomi = await ownPassword("naomi.owner@example.nl", await create("Naomi Owner", "naomi.owner@example.nl"));
  const maikelTemp = await create("Maikel Owner", "maikel.owner@example.nl");
  for (const h of [kwafie, naomi]) expect((await request.post(`${API}/api/config/root-causes/review`, { headers: h, data: { decision: "agree" } })).ok()).toBe(true);

  await openSignedOut(page);                                                                     // Maikel signs in on the real sign-in screen
  await page.getByLabel("Work e-mail address").fill("maikel.owner@example.nl");
  await page.getByLabel("Password", { exact: true }).fill(maikelTemp);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Current password").fill(maikelTemp);
  await page.getByLabel("New password", { exact: true }).fill("maikel-own-password-1");
  await page.getByLabel("Repeat new password").fill("maikel-own-password-1");
  await page.getByRole("button", { name: "Save password" }).click();
  await page.getByRole("button", { name: "Root causes" }).click();

  const panel = page.getByLabel("Agreement on this list");
  await expect(panel.getByText("Draft", { exact: true })).toBeVisible();
  await expect(panel.getByText("2 of 3 process owners have agreed to this version of the list.")).toBeVisible();
  await expect(panel.getByText("Kwafie Owner")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Request changes" })).toBeDisabled();           // asking for changes needs a comment
  await panel.getByRole("button", { name: "I agree with this list" }).click();
  await expect(panel.getByText("Agreed", { exact: true })).toBeVisible();                         // three of three
  await expect(panel.getByText(/3 of 3 process owners have agreed/)).toBeVisible();
  await expect(panel.getByText("Maikel Owner")).toBeVisible();

  await page.getByRole("button", { name: "About" }).click();                                      // the status is also on the About page
  await expect(page.getByText(/Agreed: 3 of 3 process owners/)).toBeVisible();

  await openApp(page, "demo.admin");                                                              // an administrator can do everything the other roles can, so can agree too
  await page.getByRole("button", { name: "Root causes" }).click();
  await expect(page.getByRole("button", { name: "I agree with this list" })).toHaveCount(1);
});

test("T51 the rule owner signs off the repeat rule and the business owner records go/no-go: real accounts", async ({ page, request }) => {
  const makeUser = async (name: string, email: string, role: string) => {
    const r = await (await request.post(`${API}/api/users`, { headers: ADMIN, data: { name, email, function: null, role } })).json();
    return r.temporary_password as string;
  };
  const signIn = async (email: string, temp: string, own: string) => {                           // sign in on the real screen, choose an own password
    await openSignedOut(page);
    await page.getByLabel("Work e-mail address").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(temp);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByLabel("Current password").fill(temp);
    await page.getByLabel("New password", { exact: true }).fill(own);
    await page.getByLabel("Repeat new password").fill(own);
    await page.getByRole("button", { name: "Save password" }).click();
  };
  const juulTemp = await makeUser("Juul Rule", "juul.rule@example.nl", "rule_owner");
  const glennTemp = await makeUser("Glenn Business", "glenn.business@example.nl", "business_owner");

  await signIn("juul.rule@example.nl", juulTemp, "juul-own-password-1");                         // lands on the rule page
  const rule = page.getByLabel("Sign-off of this repeat rule");
  await expect(rule.getByText("Draft", { exact: true })).toBeVisible();
  await rule.getByRole("button", { name: "Sign off this rule" }).click();
  await expect(rule.getByText("Signed off", { exact: true })).toBeVisible();
  await expect(rule.getByText("Juul Rule")).toBeVisible();
  await page.getByLabel("Lookback").fill("45");                                                   // an edit voids the sign-off
  await page.getByRole("button", { name: /Update/ }).click();
  await expect(rule.getByText("Draft", { exact: true })).toBeVisible();
  await expect(rule.getByText(/for an earlier version of the rule/)).toBeVisible();
  await rule.getByRole("button", { name: "Sign off this rule" }).click();
  await expect(rule.getByText("Signed off", { exact: true })).toBeVisible();

  await signIn("glenn.business@example.nl", glennTemp, "glenn-own-password-1");                   // lands on the readout
  await expect(page.getByRole("heading", { name: "Readout for the go/no-go decision" })).toBeVisible();
  await expect(page.getByText("Repeat rule signed off")).toBeVisible();
  await expect(page.getByText("Cause list agreed")).toBeVisible();
  await page.getByLabel("Reason (required)").fill("Go once the cause list is agreed");
  await page.getByLabel("Decision", { exact: true }).selectOption("conditional");
  await page.getByRole("button", { name: "Record decision" }).click();
  await expect(page.getByText("Go with conditions · ")).toBeVisible();
  await expect(page.getByText("Go once the cause list is agreed")).toBeVisible();

  await openApp(page, "demo.admin");                                                              // an administrator can also record the decision
  await page.getByRole("button", { name: "Readout" }).click();
  await expect(page.getByRole("button", { name: "Record decision" })).toHaveCount(1);
});

test("T52 FR-04: every prefillable field is filled after a customer-number match, and each one can be edited", async ({ page }) => {
  const exact = (pg: Page, label: string) => pg.locator(".row").filter({ has: pg.locator("label", { hasText: new RegExp(`^${label}$`) }) });
  await openApp(page);
  await search(page, "100014");                                                                    // two sites, no site in the search
  await selectFirst(page);
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Europe/Amsterdam" });
  await expect(page.getByLabel("Site", { exact: true })).toHaveValue("C014-S1");                    // from the latest order
  await expect(page.getByLabel("Contract")).not.toHaveValue("");
  await expect(page.getByLabel("Order", { exact: true })).not.toHaveValue("");
  await expect(exact(page, "Container")).not.toContainText("–");
  await expect(page.getByLabel("Channel")).toHaveValue("phone");
  await expect(page.getByLabel("Registration date")).toHaveValue(today);                            // today, not the demo clock
  await expect(page.getByLabel("Registered by")).toHaveValue("demo.emp.a1");
  for (const label of ["Customer", "Site", "Contract", "Order", "Channel", "Registration date", "Registered by"])
    await expect(field(page, label).first()).toContainText(/Prefilled|Default/);

  const other = page.getByLabel("Registered by").locator("option").filter({ hasNotText: "Demo Employee A1" }).first();   // edit each
  await page.getByLabel("Registered by").selectOption(await other.getAttribute("value") as string);
  await expect(exact(page, "Registered by")).toContainText("Edited");
  const day = new Date(Date.now() - 86400000).toLocaleDateString("en-CA", { timeZone: "Europe/Amsterdam" });
  await page.getByLabel("Registration date").fill(day);
  await expect(exact(page, "Registration date")).toContainText("Edited");
  await page.getByLabel("Channel").selectOption("email");
  await expect(exact(page, "Channel")).toContainText("Edited");
  await page.getByLabel("Site", { exact: true }).selectOption("C014-S2");                           // the contract and order follow the site
  await expect(exact(page, "Site")).toContainText("Edited");
  await expect(page.getByLabel("Order", { exact: true })).not.toHaveValue("");
  const orders = await page.getByLabel("Order", { exact: true }).locator("option").count();
  await page.getByLabel("Order", { exact: true }).selectOption({ index: orders - 1 });
  await expect(exact(page, "Order")).toContainText("Edited");
  const contracts = await page.getByLabel("Contract").locator("option").count();
  await page.getByLabel("Contract").selectOption({ index: contracts - 1 });
  await expect(exact(page, "Contract")).toContainText("Edited");

  await page.getByRole("button", { name: "Change customer" }).click();                              // the customer: choose another one
  await search(page, "100016");
  await selectFirst(page);
  await expect(exact(page, "Customer")).toContainText("Bos Fruitgroothandel");
  await expect(page.getByLabel("Site", { exact: true })).not.toHaveValue("");
});

test("T53 FR-05: choosing each complaint type applies its documented defaults; typed values stay; the table is on the About page", async ({ page }) => {
  const exact = (label: string) => page.locator(".row").filter({ has: page.locator("label", { hasText: new RegExp(`^${label.replace(/[()]/g, "\\$&")}$`) }) });
  await openApp(page);
  await search(page, "100018");
  await selectFirst(page);
  await expect(page.getByLabel("Priority")).toHaveValue("normal");                                  // before a type: status and priority are there
  await expect(exact("Response target (days)")).toContainText("–");
  const want: Record<string, [string, string, string]> = {                                          // type -> owner team, response target, label
    service: ["operations", "2", "Collection service"], billing: ["customer_service", "5", "Billing"], conduct: ["customer_service", "3", "Conduct / other"] };
  for (const [type, [team, days]] of Object.entries(want)) {
    await page.getByLabel("Complaint type").selectOption(type);
    await expect(page.getByLabel("Owner team")).toHaveValue(team);
    await expect(exact("Owner team")).toContainText("Default");
    await expect(exact("Response target (days)")).toContainText(days);
    await expect(exact("Response target (days)")).toContainText("Default");
    await expect(page.getByLabel("Priority")).toHaveValue("normal");
    await expect(exact("Status")).toContainText("open");
    await expect(page.getByLabel("Channel")).toHaveValue("phone");                                  // the customer is on the phone, whatever the type
  }
  await page.getByLabel("Priority").selectOption("high");                                           // typed by hand: stays when the type changes
  await page.getByLabel("Complaint type").selectOption("service");
  await expect(page.getByLabel("Priority")).toHaveValue("high");
  await expect(exact("Priority")).toContainText(/Edited|Typed/);
  await expect(page.getByLabel("Owner team")).toHaveValue("operations");                            // the rest follows the new type

  await page.getByRole("button", { name: "About" }).click();                                        // documented in the app too
  const table = page.getByLabel("Defaults per complaint type");
  await expect(table.getByRole("row", { name: /Billing.*email.*customer_service.*5/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Collection service.*operations.*2/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Conduct \/ other.*customer_service.*3/ })).toBeVisible();
});

test("T54 FR-06: a marker on every field shows prefilled, default, suggested, typed or edited, and the log records the same", async ({ page, request }) => {
  const row = (label: string) => page.locator(".row").filter({ has: page.locator("label", { hasText: new RegExp(`^${label}$`) }) });
  await openApp(page);
  await search(page, "100019");
  await selectFirst(page);
  await expect(page.getByRole("note")).toContainText("Marker per field");                              // a legend explains the markers
  for (const label of ["Customer", "Customer number", "Site", "Contract", "Order", "Container", "Registered by", "Registration date"])
    await expect(row(label).first()).toContainText("Prefilled");                                       // from the customer data
  for (const label of ["Channel", "Priority", "Status"]) await expect(row(label)).toContainText("Default");   // from the complaint type / start
  await expect(row("Complaint type")).toContainText("Blank");
  await page.getByLabel("Channel").selectOption("email");                                              // the employee changes a filled value
  await expect(row("Channel")).toContainText("Edited");
  await page.getByLabel("Complaint type").selectOption("service");
  await expect(row("Complaint type")).toContainText("Typed");                                          // chosen by hand
  await expect(row("Owner team")).toContainText("Default");

  await next(page);                                                                                    // describe
  await expect(page.getByText("Blank", { exact: true }).first()).toBeVisible();
  await page.getByLabel("Complaint description").fill("The container at our depot was not emptied on Tuesday, it was missed again.");
  await expect(page.locator("section").getByText("Typed", { exact: true }).first()).toBeVisible();     // the description is typed
  await page.getByRole("button", { name: "Analyse and continue", exact: true }).click();

  await expect(row("What")).toContainText("Suggested");                                                // the assistant's text, kept
  await expect(row("Container no.")).toContainText("Prefilled");                                       // from the order
  await expect(row("Cause")).toContainText("Suggested");
  await page.getByLabel("Impact").fill("Overflowing bin, customer upset");
  await expect(row("Impact")).toContainText("Edited");                                                 // the assistant's text, changed
  await page.getByRole("radio", { name: /Late collection/ }).first().check();
  await expect(row("Cause")).toContainText("Edited");

  await next(page);                                                                                    // repeat check and save: the overview carries markers too
  const overview = page.locator("dl");
  for (const [label, marker] of [["Customer", "Prefilled"], ["Site", "Prefilled"], ["Channel", "Edited"], ["Complaint type", "Typed"],
                                 ["Cause", "Edited"], ["Complaint description", "Typed"], ["Summary", "Edited"]])
    await expect(overview.locator("dt", { hasText: new RegExp(`^${label}$`) }).locator("xpath=following-sibling::dd[1]")).toContainText(marker);
  await save(page).click();
  await saved(page);
  const id = (await page.getByRole("status").innerText()).match(/COM-\d+/)![0];

  const csv = await (await request.get(`${API}/api/export/suggestions.csv`, { headers: ADMIN })).text();   // the log, as the team lead / Power BI see it
  const rows = csv.split("\n").filter((l) => l.startsWith(id + ","));
  const line = (field: string) => rows.find((l) => l.split(",")[6] === field) || "";
  expect(line("customer_id")).toContain(",prefilled,accepted");
  expect(line("priority")).toContain(",default,accepted");
  expect(line("channel")).toContain(",edited,changed");
  expect(line("complaint_type")).toContain(",manual,typed");
  expect(line("description")).toContain(",manual,typed");
  expect(line("summary")).toContain(",edited,changed");
  expect(line("root_cause")).toContain(",edited,changed");
  expect(rows.length).toBe(15);                                                                         // every tracked field is in the log
});

test("T55 FR-08: the summary can be edited before saving, and a process owner rates it with an explicit Usable / Not usable choice", async ({ page }) => {
  await openApp(page);
  await search(page, "100020");
  await selectFirst(page);
  await describe(page, "The container at our depot was not emptied on Tuesday, it was missed again.", "en");
  await expect(page.getByLabel("What", { exact: true })).not.toHaveValue("");                       // the four template fields are filled
  for (const l of ["Where", "When", "Impact"]) await expect(page.getByLabel(l, { exact: true })).toBeVisible();
  await page.getByLabel("What", { exact: true }).fill("Missed collection on Tuesday (edited by the employee)");   // editable
  await next(page);
  await save(page).click();
  await saved(page);

  await openApp(page, "demo.evaluator");                                                             // a process owner (evaluator role)
  await page.getByRole("button", { name: "Evaluation" }).click();
  const cards = page.locator("article.card > .card").filter({ has: page.locator("fieldset") });          // one card per complaint
  const card = cards.filter({ hasText: "What" }).first();                                            // a card with a saved summary
  await expect(card.locator("dt", { hasText: "What" })).toBeVisible();                              // the summary is shown labelled
  await expect(page.getByText(/Usable = you would save the summary/)).toBeVisible();                // what "usable" means
  await expect(card.getByRole("radio", { name: "Usable", exact: true })).not.toBeChecked();          // nothing is pre-ticked
  await expect(card.getByRole("radio", { name: "Not usable" })).not.toBeChecked();
  await expect(card.getByRole("button", { name: "Save label" })).toBeDisabled();                     // no rating without a choice
  const id = (await card.locator("b").first().innerText()).trim();
  await card.getByRole("radio", { name: "Not usable" }).check();
  await expect(card.getByRole("button", { name: "Save label" })).toBeEnabled();                      // a cause is optional
  await card.getByRole("button", { name: "Save label" }).click();
  await expect(page.getByText("Recorded")).toBeVisible();
  await expect(cards.filter({ hasText: id })).toHaveCount(0);   // rated: gone from this rater's list
  await expect(page.getByText("Usable summaries")).toBeVisible();
});

test("T56 FR-09: the suggested type and the top causes with a one-line reason are shown on Classify, and the summary follows", async ({ page }) => {
  await openApp(page);
  await search(page, "100021");
  await selectFirst(page);
  await describe(page, "The container at our depot was not emptied on Tuesday, it was missed again.", "en");
  await expect(page.getByText("Top suggestions")).toBeVisible();
  const picks = page.getByRole("radio", { name: /\(\d+% – .+\)/ });                                     // each suggestion: cause, confidence, reason
  expect(await picks.count()).toBeGreaterThanOrEqual(1);
  expect(await picks.count()).toBeLessThanOrEqual(3);
  await expect(page.getByLabel("Complaint type").first()).toHaveValue("service");                        // the type is suggested too
  await expect(page.getByRole("heading", { name: /Summary/ })).toBeVisible();                           // the summary fills in behind the suggestion
  await expect(page.getByRole("button", { name: "Next", exact: true })).toBeEnabled();
});

test("T57 FR-13: the rule owner reviews who disputed which repeat link and why", async ({ page, request }) => {
  const emp = { "X-Demo-User": "demo.emp.a1" };
  const saved = await request.post(`${API}/api/complaints`, { headers: emp, data: {
    customer_id: "C006", site_id: "C006-S1", root_cause: "late", channel: "phone", complaint_type: "service", description: "Late again.",
    repeat_decisions: [{ prior_complaint_id: "COM-SEED-6", decision: "confirm" }, { prior_complaint_id: "COM-SEED-7", decision: "reject", reason: "Different container, T57" }] } });
  expect(saved.ok()).toBe(true);
  await openApp(page, "demo.admin");                                                                 // an administrator may edit the rule and sees what the rule owner sees
  await page.getByRole("button", { name: "Configuration" }).click();
  const card = page.locator("article.card", { hasText: "Repeat disputes" });
  await expect(card.locator("th", { hasText: "Linked earlier complaint" })).toBeVisible();
  const row = card.getByRole("row", { name: /COM-SEED-7/ }).first();
  await expect(row).toContainText("Not a repeat");
  await expect(row).toContainText("Different container, T57");
  await expect(row).toContainText("Demo Employee A1");                                              // who decided
  await expect(row).toContainText("draft-juul-v1");                                                  // under which rule version
  await expect(card.getByRole("row", { name: /COM-SEED-6/ }).first()).toContainText("Confirm repeat");
  await expect(card.getByRole("button", { name: "Export disputes CSV" })).toBeVisible();
});

test("T58 Audit Trail: the administrator sees every saved record and how it was made; other roles do not see the page", async ({ page, request }) => {
  const emp = { "X-Demo-User": "demo.emp.a1" };
  const sid = (await (await request.post(`${API}/api/sessions`, { headers: emp, data: { mode: "assistant" } })).json()).session_id;
  const saved = await (await request.post(`${API}/api/complaints`, { headers: emp, data: {
    customer_id: "C008", site_id: "C008-S1", channel: "phone", complaint_type: "service", root_cause: "missed", description: "Audit trail test: container missed.",
    session_id: sid, field_provenance: { customer_id: "prefilled", channel: "default", description: "manual", root_cause: "suggested" } } })).json();

  await openApp(page, "demo.emp.a1");                                                                 // an employee has no Audit Trail
  await expect(page.getByRole("button", { name: "Audit Trail" })).toHaveCount(0);
  await openApp(page, "demo.evaluator");
  await expect(page.getByRole("button", { name: "Audit Trail" })).toHaveCount(0);

  await openApp(page, "demo.admin");
  const menu = await page.locator("nav.sidebar button").allInnerTexts();
  expect(menu.indexOf("Audit Trail")).toBe(menu.indexOf("History") + 1);                              // right below History
  await page.getByRole("button", { name: "Audit Trail" }).click();
  await expect(page.getByRole("heading", { name: "Audit Trail" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText(/\d+ saved records/);
  const first = page.locator("tbody tr").first();
  await expect(first).toContainText(saved.id);                                                         // the newest registration comes first
  await expect(first).toContainText("Registered");
  await expect(page.locator("tbody").getByText("Synthetic history").first()).toBeVisible();            // the seeded history is there too

  await first.getByRole("button", { name: saved.id }).click();                                         // open it
  const detail = page.locator(".audit-detail");
  await expect(detail.getByText("PROVISIONAL_ComplaintId")).toBeVisible();
  await expect(detail.getByText("Audit trail test: container missed.")).toBeVisible();
  await expect(detail.getByText("Every required field is filled.")).toBeVisible();
  await expect(detail.locator(".origins li", { hasText: "Channel" })).toContainText("Default");        // how each field was filled
  await expect(detail.locator(".origins li", { hasText: "Description" })).toContainText("Typed");
  await expect(detail.getByText("Record saved")).toBeVisible();                                        // the audit-log events about it
  await expect(detail.getByText("Repeat rule applied")).toBeVisible();

  await page.getByLabel("Record, customer name or number").fill(saved.id);                             // search
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("status")).toContainText("1 saved records");
  await expect(page.getByRole("button", { name: "Export records CSV" })).toBeVisible();
});

test("T59 FR-15: a registration made on the screen leaves a complete log: time per step, prefilled fields, suggestions shown, accepted or changed", async ({ page }) => {
  await openApp(page);
  await search(page, "100013");
  await selectFirst(page);
  await page.getByLabel("Channel").selectOption("email");                                             // a change during the registration
  await describe(page, "The container at our depot was not emptied on Tuesday, it was missed again.", "en");
  await page.getByLabel("Impact", { exact: true }).fill("Overflowing bin, customer upset");           // the assistant's summary, changed
  await next(page);
  await save(page).click();
  await saved(page);
  const id = (await page.getByRole("status").innerText()).match(/COM-\d+/)![0];

  await openApp(page, "demo.admin");
  await page.getByRole("button", { name: "Audit Trail" }).click();
  await page.getByLabel("Record, customer name or number").fill(id);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.locator("tbody tr").first()).toContainText("Log complete");                        // the list says so
  await page.getByRole("button", { name: id }).click();
  const log = page.getByLabel("Registration log");
  await expect(log).toContainText("Log complete");
  for (const step of ["Find customer", "Review details", "Describe complaint", "Classify", "Repeat check and save"])
    await expect(log.getByRole("row", { name: new RegExp(`^${step}`) })).toBeVisible();               // time per step: all five
  await expect(log).toContainText(/\d+ prefilled from the customer data and \d+ defaulted/);          // fields prefilled
  await expect(log).toContainText("Channel → Edited");                                                 // changed during the registration
  await expect(log.getByRole("heading", { name: "Suggestions shown" })).toBeVisible();                 // suggestions shown with their reasons
  await expect(log.getByRole("row", { name: /Missed collection|Niet ingezameld|Missed/ }).first()).toBeVisible();
  await expect(log).toContainText("kept the first suggestion");                                        // accepted
  await expect(log).toContainText("the suggested summary was changed (impact)");                       // changed
});

test("T61 live registration clock: visible from the start, ticks, shows the time per step, stops at save and matches the logged time", async ({ page, request }) => {
  await openApp(page);
  const clock = page.getByRole("timer");
  await expect(clock).toBeVisible();                                                                 // shown from the moment the form opens, at 00:00
  const secs = async () => { const [m, s] = (await clock.locator(".reg-clock-total b").innerText()).split(":").map(Number); return m * 60 + s; };
  await page.waitForTimeout(2300);
  expect(await secs()).toBe(0);                                                                      // it waits: opening the screen does not start it
  await expect(clock).toContainText("Starts when you begin");
  await page.getByLabel(SEARCH).click();                                                             // the first interaction starts it
  await page.waitForTimeout(2300);
  expect(await secs()).toBeGreaterThanOrEqual(2);                                                    // it is running
  await expect(clock).not.toContainText("Starts when you begin");
  await expect(clock.locator("li.now")).toContainText("Find customer");
  await search(page, "100013");
  await selectFirst(page);
  await expect(clock.locator("li.now")).toContainText("Review details");                             // the current step moves with the registration
  await expect(clock.locator("li", { hasText: "Find customer" })).not.toContainText("–");            // the finished step keeps its time
  await expect(clock.locator("li", { hasText: "Classify" })).toContainText("–");                     // steps not reached yet show a dash
  await describe(page, "The container at our depot was not emptied on Tuesday, it was missed again.", "en");
  await expect(clock.locator("li.now")).toContainText("Classify");
  await page.getByRole("button", { name: "Back", exact: true }).click();                             // going back keeps counting
  await expect(clock.locator("li.now")).toContainText("Describe complaint");
  await expect(clock.locator("li", { hasText: "Describe complaint" })).not.toContainText("–");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.waitForTimeout(500);
  await next(page);
  const before = await secs();
  await save(page).click();
  await saved(page);
  const stopped = page.getByRole("timer");
  await expect(stopped).toContainText("Registered in");                                              // the clock stays on the saved screen, stopped
  const finalSecs = await (async () => { const [m, s] = (await stopped.locator(".reg-clock-total b").innerText()).split(":").map(Number); return m * 60 + s; })();
  expect(finalSecs).toBeGreaterThanOrEqual(before);
  await page.waitForTimeout(1500);
  expect(await stopped.locator(".reg-clock-total b").innerText()).toBe(`${String(Math.floor(finalSecs / 60)).padStart(2, "0")}:${String(finalSecs % 60).padStart(2, "0")}`);   // no longer running

  const id = (await page.getByRole("status").innerText()).match(/COM-\d+/)![0];                       // the same registration as the server logged it
  const log = (await (await request.get(`${API}/api/audit/records/${id}`, { headers: ADMIN })).json()).log;
  expect(Math.abs(log.total_seconds - finalSecs)).toBeLessThanOrEqual(3);
  await page.getByRole("button", { name: "New registration" }).click();
  await expect(page.getByRole("timer")).toContainText("Starts when you begin");                       // a new registration starts a new clock, waiting for the first click
});

test("T62 the clock can be switched off by one setting", async ({ page }) => {
  await page.route("**/api/config", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: { ...body, ui: { show_timer: false } } });
  });
  await openApp(page);
  await expect(page.getByText("Find customer").first()).toBeVisible();
  await expect(page.getByRole("timer")).toHaveCount(0);
});

test("T63 FR-15: a registration that was started but not saved is listed on the Audit Trail with its log", async ({ page, request }) => {
  const emp = { "X-Demo-User": "demo.emp.a1" };
  const sid = (await (await request.post(`${API}/api/sessions`, { headers: emp, data: { mode: "assistant" } })).json()).session_id;
  const card = (await (await request.get(`${API}/api/customers/search?q=100013`, { headers: emp })).json()).candidates[0];
  await request.post(`${API}/api/prefill`, { headers: emp, data: { customer_id: card.customer_id, origin: "search", guess_site: true, session_id: sid } });
  for (const [a, b] of [["find_customer", "review_details"], ["review_details", "describe_complaint"]]) {
    await request.post(`${API}/api/sessions/${sid}/events`, { headers: emp, data: { type: "step_completed", step: a } });
    await request.post(`${API}/api/sessions/${sid}/events`, { headers: emp, data: { type: "step_entered", step: b } });
  }
  await request.post(`${API}/api/sessions/${sid}/complete`, { headers: emp, data: { outcome: "abandoned" } });

  await openApp(page, "demo.admin");
  await page.getByRole("button", { name: "Audit Trail" }).click();
  await page.getByRole("tab", { name: "Registrations not saved" }).click();
  await expect(page.getByRole("status")).toContainText(/\d+ registrations not saved/);
  const row = page.locator("tbody tr", { hasText: sid.slice(0, 8) });
  await expect(row).toContainText("Abandoned");
  await expect(row).toContainText("Describe complaint");                                              // where it stopped
  await page.getByRole("tab", { name: "Saved records" }).click();
  await expect(page.getByRole("status")).toContainText(/saved records/);
});

test("T64 FR-17 dashboard: time per registration, Other share, suggestion acceptance and repeat rate, overall and by user group", async ({ page, request }) => {
  const emp = { "X-Demo-User": "demo.emp.b1" };                                                      // a user group of its own (group_b)
  for (const [cust, site, text] of [["C005", "C005-S1", "Container missed again."], ["C008", "C008-S1", "Container missed again."]]) {
    const sid = (await (await request.post(`${API}/api/sessions`, { headers: emp, data: { mode: "assistant" } })).json()).session_id;
    const cls = (await (await request.post(`${API}/api/complaints/classify`, { headers: emp, data: { text, session_id: sid } })).json()).result.candidates;
    await request.post(`${API}/api/complaints`, { headers: emp, data: { customer_id: cust, site_id: site, channel: "phone", complaint_type: "service", root_cause: cls[0].root_cause_id,
      description: text, session_id: sid, field_provenance: { root_cause: "suggested", summary: "suggested", complaint_type: "suggested" } } });
  }
  await openApp(page, "demo.admin");
  await page.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByText("Duration (s)").first()).toBeVisible();                               // time per registration
  const acc = page.getByLabel("Suggestion acceptance");
  for (const l of ["First cause kept", "Cause within top 3", "Summary kept", "Type kept"]) await expect(acc.getByText(l)).toBeVisible();
  await expect(acc.locator(".bar-row", { hasText: "First cause kept" })).toContainText("%");
  const groups = page.locator("article.card", { hasText: "By user group" });
  for (const h of ["Duration (s)", "Other", "First cause kept", "Cause within top 3", "Summary kept", "Repeat"]) await expect(groups.locator("th", { hasText: h }).first()).toBeVisible();
  const row = groups.locator("tbody tr", { hasText: "group_b" });
  await expect(row).toContainText("%");                                                              // shares for that group, with their n
  await expect(row).toContainText("n=");
});

test("T65 FR-18/19/20 root-cause analysis screen: themes with coverage, a proposed list, agreement tied to that list, and the re-label test", async ({ page, request }) => {
  const emp = { "X-Demo-User": "demo.emp.a1" };
  for (const reason of ["A seagull built a nest in the container", "Mice found in the paper container", "Road closure blocked the truck", "Parade event, street afgesloten"]) {
    const r = await request.post(`${API}/api/complaints`, { headers: emp, data: { customer_id: "C006", site_id: "C006-S1", channel: "phone", complaint_type: "service", root_cause: "other", other_reason: reason, description: reason } });
    expect(r.status()).toBe(201);
  }
  await openApp(page, "demo.admin");
  await page.getByRole("button", { name: "Root-cause analysis" }).click();
  await page.getByRole("button", { name: "Find themes" }).click();
  await expect(page.getByTestId("rca-coverage")).toContainText("Coverage");
  await expect(page.locator("article.card", { hasText: "Themes in" }).locator("tbody tr").first()).toBeVisible();
  await page.getByRole("button", { name: "Propose a list" }).click();
  await expect(page.getByTestId("rca-state")).toHaveText("draft");
  await expect(page.getByText("Agreed by 0 of 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Agree to this list" })).toHaveCount(1);            // the administrator can do everything the other roles can
  await expect(page.getByRole("button", { name: "Re-label with the current list" })).toBeDisabled();   // no expert labels yet
  await openApp(page, "demo.evaluator");
  await page.getByRole("button", { name: "Root-cause analysis" }).click();
  await page.getByRole("button", { name: "Agree to this list" }).click();
  await expect(page.getByText("Agreed by 1 of 3")).toBeVisible();
});

test("T66 repeat override: a disputed link waits for the weekly review, the rule owner records it, the evaluator only sees it", async ({ page, request }) => {
  const emp = { "X-Demo-User": "demo.emp.a1" };
  const mk = async () => (await (await request.post(`${API}/api/complaints`, { headers: emp, data: { customer_id: "C007", site_id: "C007-S1", channel: "phone", complaint_type: "service", root_cause: "late", description: "late again" } })).json());
  const first = await mk();
  const second = await mk();
  await request.post(`${API}/api/repeat-disputes`, { headers: emp, data: { complaint_id: second.id, prior_complaint_id: first.id, decision: "reject", reason: "different pickup" } });
  await openApp(page, "demo.evaluator");
  await page.getByRole("button", { name: "Evaluation" }).click();
  const bar = page.getByTestId("dispute-review");
  await expect(bar).toContainText("Weekly review due");
  await expect(bar.getByRole("button", { name: "Mark all as reviewed" })).toHaveCount(0);            // the evaluator can see, not record
  await openApp(page, "demo.admin");
  await page.getByRole("button", { name: "Configuration" }).click();
  const bar2 = page.getByTestId("dispute-review");
  await bar2.getByLabel("Review note (optional)").fill("week 44");
  await bar2.getByRole("button", { name: "Mark all as reviewed" }).click();
  await expect(bar2).toContainText("Weekly review up to date");
  await expect(page.locator("tbody tr", { hasText: "different pickup" })).toContainText("Reviewed");
});

test("T67 a registration left over from before (its session gone from the server) does not break the next one or keep its old clock", async ({ page }) => {
  await openApp(page);
  await page.evaluate(() => sessionStorage.setItem("cra.register", JSON.stringify({ sessionId: "gone-session", openedAt: Date.now() - 3600_000, step: 0,
    visits: [{ step: "find_customer", from: Date.now() - 3600_000, to: null }] })));
  await page.getByRole("button", { name: "History" }).click();
  await page.getByRole("button", { name: "Register" }).click();                                     // the form opens with the old state
  await search(page, "100013");
  await page.getByRole("button", { name: /^(Select|Use this customer)$/ }).first().click();
  await expect(page.getByRole("alert")).toContainText("no longer available");                       // a clear message, not "Session not found"
  const clock = page.getByRole("timer");
  const secs = async () => { const [m, s] = (await clock.locator(".reg-clock-total b").innerText()).split(":").map(Number); return m * 60 + s; };
  expect(await secs()).toBeLessThan(60);                                                            // the old hour is gone; a new clock started
  await search(page, "100013");
  await selectFirst(page);
  await expect(clock.locator("li.now")).toContainText("Review details");                             // and the registration goes on normally
});

test("T68 the baseline form offers the groups employees really belong to (their function), so it can be compared with their registrations", async ({ page, request }) => {
  await openApp(page, "demo.evaluator");
  await page.getByRole("button", { name: "Evaluation" }).click();
  const group = page.getByLabel("User group");
  await expect(group.locator("option")).toContainText(["customer_service", "sales", "site_operations"]);
  await group.selectOption("sales");
  await page.getByLabel("Seconds").first().fill("240");
  await page.getByRole("button", { name: "Submit" }).nth(1).click();
  await expect(page.getByText("Recorded").first()).toBeVisible();
  const base = await (await request.get(`${API}/api/baseline`, { headers: ADMIN })).json();
  expect(base.by_group.sales.mean_seconds).toBe(240);
});

test("T69 the dashboard shows the Power BI feed: the tables to download, the address and the header", async ({ page }) => {
  await openApp(page, "demo.admin");
  await page.getByRole("button", { name: "Dashboard" }).click();
  const card = page.getByLabel("Power BI");
  await expect(card).toContainText("/api/reporting/");
  await expect(card).toContainText("X-Reporting-Key");
  for (const t of ["group_summary", "sessions", "suggestions", "employees", "baseline", "interviews", "ratings"]) await expect(card.getByRole("button", { name: `${t}.csv` })).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), card.getByRole("button", { name: "group_summary.csv" }).click()]);
  expect(download.suggestedFilename()).toBe("group_summary.csv");
  await openApp(page, "demo.lead");                                                                 // a team lead sees their own team's tables only
  await page.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByLabel("Power BI").getByRole("button", { name: "baseline.csv" })).toHaveCount(0);
  await expect(page.getByLabel("Power BI").getByRole("button", { name: "group_summary.csv" })).toBeVisible();
});

test("T70 the dashboard has a team report: time per step and every suggestion accepted or changed, for the lead's own team", async ({ page }) => {
  await openApp(page, "demo.lead");
  await page.getByRole("button", { name: "Dashboard" }).click();
  const report = page.getByLabel("Team report");
  await expect(report.getByRole("heading", { name: "Team report" })).toBeVisible();
  await expect(report.getByRole("heading", { name: "Time per step (seconds)" })).toBeVisible();
  await expect(report.getByRole("heading", { name: "Suggestions by field" })).toBeVisible();
  await expect(report.getByRole("heading", { name: "Every suggestion" })).toBeVisible();
  await expect(report.locator("th", { hasText: "Find customer" })).toBeVisible();
  await expect(report.getByRole("cell", { name: "Average per step" })).toBeVisible();
  await expect(report.locator("th", { hasText: /^Team$/ })).toHaveCount(0);                  // one team only: no team column
  await report.getByLabel("Outcome").selectOption("accepted");
  await expect(report.locator("tbody tr .out-badge").first()).toHaveText("Accepted");
});
