import { expect, test } from "@playwright/test";

function durationLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} hr ${remainder} min` : `${hours} hr`;
}

function durationMinutes(start: string, shutdown: string): number {
  const [startHour, startMinute] = start.split(":").map(Number);
  const [endHour, endMinute] = shutdown.split(":").map(Number);
  return endHour * 60 + endMinute - startHour * 60 - startMinute;
}

test("runtime schedule saves, reloads, validates backup limits, and restores the original", async ({ page }) => {
  await page.goto("/settings");

  const section = page.getByRole("region", { name: "Application Runtime Schedule" });
  await expect(section).toBeVisible();
  const start = page.getByLabel("Daily start time");
  const shutdown = page.getByLabel("Daily shutdown time");
  await expect(start).toBeVisible();
  await expect(shutdown).toBeVisible();
  await expect(section.getByRole("heading", { name: "Current saved schedule" })).toBeVisible();
  await expect(section.getByRole("heading", { name: "Host-applied schedule" })).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "horizontal overflow on /settings").toBeLessThanOrEqual(1);

  const originalStart = await start.inputValue();
  const originalShutdown = await shutdown.inputValue();
  const savedScheduleText = section.locator(".runtime-saved p").first();
  await expect(savedScheduleText).toContainText(`${originalStart}–${originalShutdown}`);

  expect(originalStart).toMatch(/^\d{2}:\d{2}$/);
  expect(originalShutdown).toMatch(/^\d{2}:\d{2}$/);
  const draftStart = originalStart === "08:00" ? "07:00" : "08:00";
  const draftDuration = durationMinutes(draftStart, originalShutdown);

  try {
    await start.fill(draftStart);
    await shutdown.fill("20:00");
    await expect(
      section.getByText(
        "Shutdown before 21:00 is not supported until the approved backup-timer migration is complete.",
      ),
    ).toBeVisible();
    await expect(section.getByRole("button", { name: "Save schedule" })).toBeDisabled();

    await shutdown.fill(originalShutdown);
    await expect(section.getByText(durationLabel(draftDuration), { exact: true })).toBeVisible();
    await section.getByRole("button", { name: "Save schedule" }).click();

    await expect(savedScheduleText).toContainText(`${draftStart}–${originalShutdown}`);
    await expect(section.getByText("Waiting for host confirmation", { exact: true })).toBeVisible();
    await expect(section.getByText("Applied by host", { exact: true })).toHaveCount(0);

    await page.reload();
    await expect(start).toHaveValue(draftStart);
    await expect(shutdown).toHaveValue(originalShutdown);
    await expect(section.locator(".runtime-saved p").first()).toContainText(
      `${draftStart}–${originalShutdown}`,
    );
    await expect(section.getByText("Waiting for host confirmation", { exact: true })).toBeVisible();
    await expect(section.getByText("Applied by host", { exact: true })).toHaveCount(0);
  } finally {
    await page.goto("/settings");
    const restoreSection = page.getByRole("region", { name: "Application Runtime Schedule" });
    const restoreStart = page.getByLabel("Daily start time");
    const restoreShutdown = page.getByLabel("Daily shutdown time");
    await expect(restoreStart).toBeVisible();
    await restoreStart.fill(originalStart);
    await restoreShutdown.fill(originalShutdown);
    const saveButton = restoreSection.getByRole("button", { name: "Save schedule" });
    if (await saveButton.isEnabled()) {
      await saveButton.click();
      await expect(restoreSection.locator(".runtime-saved p").first()).toContainText(
        `${originalStart}–${originalShutdown}`,
      );
    }
  }
});
