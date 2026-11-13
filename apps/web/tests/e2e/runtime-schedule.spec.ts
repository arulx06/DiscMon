import { expect, test } from "@playwright/test";

test("runtime schedule shows saved versus host-confirmed state and validates drafts", async ({ page }) => {
  await page.goto("/settings");

  const section = page.getByRole("region", { name: "Application Runtime Schedule" });
  await expect(section).toBeVisible();
  const start = page.getByLabel("Daily start time");
  const shutdown = page.getByLabel("Daily shutdown time");
  await expect(start).toBeVisible();
  await expect(shutdown).toBeVisible();
  await expect(section.getByRole("heading", { name: "Current saved schedule" })).toBeVisible();
  await expect(section.getByRole("heading", { name: "Host-applied schedule" })).toBeVisible();

  const startValue = await start.inputValue();
  const shutdownValue = await shutdown.inputValue();
  expect(startValue).toMatch(/^\d{2}:\d{2}$/);
  expect(shutdownValue).toMatch(/^\d{2}:\d{2}$/);

  await shutdown.fill(startValue);
  await expect(section.getByText("Shutdown must be later than start on the same day.")).toBeVisible();
  await expect(section.getByRole("button", { name: "Save schedule" })).toBeDisabled();

  await shutdown.fill(shutdownValue);
  await expect(section.getByRole("button", { name: "Save schedule" })).toBeDisabled();
});
