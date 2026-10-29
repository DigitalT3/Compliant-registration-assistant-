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
const saved = (page: Page) => expect(page.getByRole("status")).toContainText(/Saved as POC-\d+ \(PoC database only\)/);

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
  await expect(page.getByText(/POC-SEED-1/)).toBeVisible();
  await expect(page.getByText("Rule draft-juul-v1: same customer, same site, same cause category, within 60 days. Provisional: to be confirmed by Juul (Renewi).")).toBeVisible();
  await page.getByRole("radio", { name: "Not a repeat" }).check();
  await page.getByLabel("Reason (required)").fill("Different container this time");
  await save(page).click();
  await saved(page);
  const disputes = await (await request.get("http://127.0.0.1:8010/api/repeat-disputes", { headers: { "X-Demo-User": "demo.emp.a1" } })).json();
  expect(disputes.items[0]).toMatchObject({ prior_complaint_id: "POC-SEED-1", decision: "reject" });
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

test("T22 plain form mode: no AI, manual cause, saved and tagged for timing", async ({ page }) => {
  await openApp(page);
  await page.getByText("Test session (optional)").click();
  await page.getByLabel("Participant").fill("P-E2E");
  await page.getByLabel("Scenario").fill("T22");
  await page.getByLabel(/^Mode/).selectOption("plain");
  await search(page, "100009");
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption("C009-S1");
  await page.getByLabel("Complaint type").selectOption("service");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel("Complaint description").fill("Container damaged by the truck.");
  await page.getByRole("button", { name: "Next", exact: true }).click();          // no "Analyse" step in plain mode
  await expect(page.getByText(/Plain form: no AI suggestions/)).toBeVisible();
  await page.getByRole("radio", { name: /Container damage/ }).check();
  await next(page);
  await save(page).click();
  await saved(page);
});

test("T23 dashboard (team lead) shows PRD targets, groups and the plain vs assistant split", async ({ page }) => {
  await openApp(page, "demo.lead");
  await page.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByRole("heading", { name: "PRD targets" })).toBeVisible();
  await expect(page.getByText(/< 10% 'Other'/)).toBeVisible();
  await page.getByLabel("Group by").selectOption("mode");
  await expect(page.getByRole("cell", { name: "plain", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "assistant", exact: true })).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "PRD targets" })).toBeVisible();          // team lead lands on the dashboard
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
  await expect(data.getByRole("tab", { name: "Contracts (2)" })).toBeVisible();
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

test("T37 the result card already shows the contract and the three latest orders (step 1)", async ({ page }) => {
  await openApp(page);
  await search(page, "100009");
  const card = page.locator(".card.found");
  await expect(card.getByText("Customer found")).toBeVisible();
  await expect(card.getByText(/Contracts:/)).toBeVisible();
  await expect(card.getByText(/CON-009-1 \(Synthetic depot 1, valid to 2027-08-24\)/)).toBeVisible();
  await expect(card.getByText("Recent orders:")).toBeVisible();
  await expect(card.locator("li")).toHaveCount(3);                                            // the three latest
  const items = await card.locator("li").allInnerTexts();
  expect(items.every((t) => /^ORD-009-\w+ · BOX-009-\d · \d{4}-\d{2}-\d{2} · \w+/.test(t))).toBe(true);   // reference · container · date · status
  const dates = items.map((t) => t.split(" · ")[2]);
  expect(dates).toEqual([...dates].sort().reverse());                                         // newest first
  await search(page, "ORD-002-10");                                                           // orders of the matched site only
  await expect(page.locator(".card.found").getByText(/Matched via order number/)).toBeVisible();
  await expect(page.locator(".card.found li").first()).toContainText("ORD-002-10");
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
  await search(page, "100009");
  await selectFirst(page);
  await page.getByLabel("Complaint type").selectOption("service");
  await describe(page, "De container is vandaag niet geleegd.", "nl");                              // no container in the text, no order chosen
  await expect(page.getByLabel("Container no.")).toHaveValue("");
  await page.getByRole("button", { name: "Back", exact: true }).click();                           // classify -> describe
  await page.getByRole("button", { name: "Back", exact: true }).click();                           // describe -> review
  const data = page.getByRole("region", { name: "Customer context" });
  await data.getByRole("tab", { name: /orders/i }).click();
  await data.getByRole("row").filter({ hasText: "BOX-009-1" }).first().getByRole("button", { name: "Use" }).click();
  await next(page);
  await next(page);                                                                                // same text: no new AI call
  await expect(page.getByLabel("Container no.")).toHaveValue("BOX-009-1");
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

test("T44 a team lead sees one team: banner, no 'group by user group', suggestions export", async ({ page }) => {
  await openApp(page, "demo.lead");
  await page.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Team: Group a" })).toBeVisible();
  const options = await page.getByLabel("Group by").locator("option").allTextContents();
  expect(options).not.toContain("User group");
  await expect(page.getByRole("button", { name: /Export suggestions CSV/ })).toBeVisible();
  await openApp(page, "demo.admin");                                                              // admins are not limited
  await page.getByRole("button", { name: "Dashboard" }).click();
  await expect(page.getByLabel("Group by").locator("option", { hasText: "User group" })).toHaveCount(1);
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
    return (await page.getByRole("status").innerText()).match(/POC-\d+/)![0];
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
  await expect(page.getByLabel("Group by").locator("option", { hasText: "User group" })).toHaveCount(0);
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

test("T48 the registration clock starts when the form opens, so finding the customer counts", async ({ page, request }) => {
  await openApp(page);
  await page.waitForTimeout(3000);                                                                // the employee takes a moment before searching
  await search(page, "100009");
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption("C009-S1");
  await page.getByRole("button", { name: "Next", exact: true }).click();                           // review -> describe: a step event closes the first step
  const rows = await (await request.get(`${API}/api/analytics/sessions`, { headers: ADMIN, params: { page_size: 1 } })).json();
  const mine = rows.items[0];
  expect(mine.step_seconds.find_customer).toBeGreaterThanOrEqual(3);                              // not the ~1 s of the lookup call
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
