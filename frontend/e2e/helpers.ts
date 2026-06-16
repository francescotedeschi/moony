import { expect, type Page } from "@playwright/test";

export async function waitForApiOk(page: Page) {
  await expect(page.getByRole("heading", { name: "moony" })).toBeVisible();
  await expect(page.locator("header .font-mono")).toContainText("ok", { timeout: 30_000 });
}

export async function startListening(page: Page) {
  const matchResponse = page.waitForResponse(
    (r) => r.url().includes("/match") && r.request().method() === "POST" && r.ok(),
    { timeout: 60_000 },
  );
  await page.getByTestId("start-listening").click();
  await matchResponse;
  await expect(page.getByTestId("now-playing")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("track-title")).not.toHaveText("", { timeout: 5_000 });
}

export async function waitForAudioReady(page: Page) {
  await expect(page.getByRole("button", { name: "Skip" })).toBeEnabled({ timeout: 60_000 });
}

/** Drag the dotted mood tracker (not a click-to-teleport on the pad). */
export async function dragTracker(page: Page, to: { x: number; y: number }) {
  const pad = page.getByTestId("emotion-pad");
  const tracker = page.getByTestId("dotted-pointer-tracker");
  await pad.scrollIntoViewIfNeeded();
  const padBox = await pad.boundingBox();
  const trackerBox = await tracker.boundingBox();
  if (!padBox || !trackerBox) throw new Error("emotion pad or tracker not visible");
  const start = {
    x: trackerBox.x + trackerBox.width / 2,
    y: trackerBox.y + trackerBox.height / 2,
  };
  const end = { x: padBox.x + padBox.width * to.x, y: padBox.y + padBox.height * to.y };
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(end.x, end.y, { steps: 12 });
  await page.mouse.up();
}

/** @deprecated Use dragTracker for mood changes; pad-only drags no longer move the tracker. */
export async function dragPad(page: Page, from: { x: number; y: number }, to: { x: number; y: number }) {
  await dragTracker(page, to);
}

export function trackTitle(page: Page) {
  return page.getByTestId("track-title");
}
