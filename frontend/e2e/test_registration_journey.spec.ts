import { expect, test } from "@playwright/test";

/**
 * T01/T10 browser acceptance: an employee completes the six-step synthetic
 * registration flow and sees deterministic repeat evidence before PoC-only save.
 */
test("T01/T10: employee can register a seeded repeat complaint through the browser", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("cra.lang", "en"));
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Complaint Registration Assistant" })).toBeVisible();
  await expect(page.getByText("Find customer", { exact: false })).toBeVisible();

  await page.getByLabel("Customer number, order, container or name").fill("100001");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const customerCandidate = page.getByText(/Fictional Delta Works 01.*100001/);
  await expect(customerCandidate).toBeVisible();

  await page.getByRole("button", { name: "Select", exact: true }).click();
  await page.getByLabel("Site").selectOption("C001-S1");
  await page.getByLabel("Complaint type").selectOption("service");
  await expect(page.getByLabel("Channel")).toHaveValue("phone");

  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel("Complaint description").fill(
    "The container at our depot was not emptied on Tuesday; the collection was missed again.",
  );
  await page.getByLabel("Text language").selectOption("en");
  await page.getByRole("button", { name: "Create summary", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Summary", exact: false })).toBeVisible();
  await expect(page.getByText("MOCK AI", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Suggest root causes", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Top suggestions", exact: false })).toBeVisible();
  await page.getByRole("radio", { name: /^Missed collection \(/ }).check();

  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText(/Repeat complaint: 1 earlier matching complaint/)).toBeVisible();
  await expect(page.getByText(/^POC-SEED-1/)).toBeVisible();

  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save to PoC database", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Save to PoC database", exact: true }).click();

  await expect(page.getByRole("status")).toContainText(/Saved as POC-\d+ \(PoC database only\)/);
  await expect(page.getByText(/Repeat complaint: 1 earlier matching complaint/)).toBeVisible();
});
