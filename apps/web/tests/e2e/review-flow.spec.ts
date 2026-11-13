import { expect, test } from "@playwright/test";

const DEMO_TITLE = "[Demo] Senior Backend Engineer";

test("review flow uses labelled demo fixtures and persists the decision", async ({
  page,
}, testInfo) => {
  await page.goto("/opportunities?include_fixtures=1");
  await expect(
    page.getByText("Demo fixtures are labelled test records. They are not real opportunities."),
  ).toBeVisible();
  await expect(page.getByText("Demo fixture", { exact: true }).first()).toBeVisible();

  await page.getByRole("link", { name: DEMO_TITLE }).click();
  await expect(page).toHaveURL(/\/opportunities\/[0-9a-f-]+$/);
  await expect(page.getByRole("heading", { name: DEMO_TITLE })).toBeVisible();
  await expect(page.getByText("Demo fixture", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Official source" })).toHaveAttribute(
    "href",
    /^https?:\/\//,
  );
  await expect(page.getByRole("link", { name: "Application page" })).toHaveAttribute(
    "href",
    /^https?:\/\/.+\/apply$/,
  );

  const note = `E2E review ${testInfo.project.name}`;
  await page.getByLabel("Decision").selectOption("watch");
  await page.getByLabel("Note").fill(note);
  await page.getByRole("button", { name: "Save review" }).click();
  await expect(page.getByText("Review saved")).toBeVisible();
  await expect(page.getByLabel("Decision")).toHaveValue("watch");
  await expect(page.getByLabel("Note")).toHaveValue(note);

  await page.goto("/opportunities?include_fixtures=1&decision=watch");
  await expect(page.getByRole("link", { name: DEMO_TITLE })).toBeVisible();
});

test("demo overview keeps its official source without an application link", async ({
  page,
}) => {
  await page.goto("/opportunities?include_fixtures=1");
  const title = "[Demo] Open Source Maintainer Residency";
  const opportunity = page.getByRole("link", { name: title, exact: true });
  await expect(opportunity).toBeVisible();
  await opportunity.click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("Demo fixture", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Official source" })).toHaveAttribute(
    "href",
    "https://example.org/discmon-demo/maintainer-residency",
  );
  await expect(page.getByRole("link", { name: "Application page" })).toHaveCount(0);
});

test("core pages render without horizontal overflow", async ({ page }) => {
  for (const path of ["/", "/opportunities?include_fixtures=1", "/sources", "/health"]) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);
  }
});
