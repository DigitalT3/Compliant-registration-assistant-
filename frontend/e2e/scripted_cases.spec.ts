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
  await page.getByRole("button", { name: "Select", exact: true }).first().click();
  await expect(page.getByText("Customer context")).toBeVisible();
}

async function describe(page: Page, text: string, lang: "en" | "nl") {
  await page.getByRole("button", { name: "Next", exact: true }).click();               // review -> describe
  await page.getByLabel("Complaint description").fill(text);
  await page.getByLabel("Text language").selectOption(lang);
  await page.getByRole("button", { name: "Analyse and continue", exact: true }).click(); // one AI call
}

const next = (page: Page) => page.getByRole("button", { name: "Next", exact: true }).click();
const save = (page: Page) => page.getByRole("button", { name: "Save to PoC database", exact: true });
const saved = (page: Page) => expect(page.getByRole("status")).toContainText(/Saved as POC-\d+ \(PoC database only\)/);

test("T01 customer number, English text, suggested cause preselected, saved", async ({ page }) => {
  await openApp(page);
  await search(page, "100009");
  await expect(page.getByText(/100009/).first()).toBeVisible();
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption("C009-S1");
  await expect(page.getByText("Container", { exact: true })).toBeVisible();
  await describe(page, "The container at our depot was not emptied on Tuesday, it was missed again.", "en");
  await expect(page.getByRole("heading", { name: /Summary/ })).toBeVisible();
  await expect(page.getByRole("radio", { name: /Missed collection/ }).first()).toBeChecked();   // confirm, don't type
  await expect(page.getByLabel("Complaint type").first()).toHaveValue("service");
  await next(page);
  await expect(page.getByText("No repeat found under the current rule.")).toBeVisible();
  await next(page);
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
  await expect(page.getByText("BOX-002-1", { exact: true })).toBeVisible();
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
  await expect(page.getByLabel("Channel")).toHaveValue("email");                  // defaults for billing
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
  await next(page); await next(page);
  await expect(save(page)).toBeDisabled();
});

test("T09 'Other' needs a reason before saving", async ({ page }) => {
  await openApp(page);
  await search(page, "100020");
  await selectFirst(page);
  await page.getByLabel("Site", { exact: true }).selectOption({ index: 1 });
  await describe(page, "A seagull built a nest under the lid of our container.", "en");
  await page.getByRole("radio", { name: /^Other$/ }).check();
  await expect(page.getByLabel(/Reason for 'Other'/)).toBeVisible();
  await page.getByLabel("Complaint type").first().selectOption("service");               // Other has no type of its own
  await next(page); await next(page);
  await expect(save(page)).toBeDisabled();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await page.getByLabel(/Reason for 'Other'/).fill("Seagull nest (synthetic)");
  await next(page); await next(page);
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
  await page.getByRole("radio", { name: "Not a repeat" }).check();
  await page.getByLabel("Reason (required)").fill("Different container this time");
  await next(page);
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
  await expect(page.getByText(/Matched via customer_number/)).toBeVisible();
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
  await next(page); await next(page);
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
});

test("T24 interface switches to Dutch", async ({ page }) => {
  await openApp(page);
  await page.getByLabel("Language").selectOption("nl");
  await expect(page.getByText("Klantnummer, order, container, naam of postcode")).toBeVisible();
  await expect(page.getByRole("button", { name: "Zoeken" })).toBeVisible();
});
