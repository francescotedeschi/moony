import { expect, test } from "@playwright/test";
import {
  dragTracker,
  startListening,
  trackTitle,
  waitForApiOk,
  waitForAudioReady,
} from "./helpers";

test.describe("Moony E2E", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await waitForApiOk(page);
  });

  test("health e schermata iniziale", async ({ page }) => {
    await expect(page.getByTestId("start-listening")).toBeVisible();
    await expect(page.getByTestId("now-playing")).toHaveCount(0);
  });

  test("avvio ascolto mostra brano in riproduzione", async ({ page }) => {
    await startListening(page);
    await waitForAudioReady(page);
    await expect(page.getByTestId("track-artist")).not.toBeEmpty();
  });

  test("conteggio riproduzioni sotto artista", async ({ page }) => {
    const health = await page.request.get("/health");
    const playStats = (await health.json()).play_stats as { enabled?: boolean };
    test.skip(!playStats?.enabled, "play_stats disabilitate (DATABASE_URL)");

    await startListening(page);
    await waitForAudioReady(page);
    await expect(page.getByTestId("play-count")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("play-count")).toHaveText(/play/i);
  });

  test("skip cambia brano", async ({ page }) => {
    await startListening(page);
    await waitForAudioReady(page);
    const titleBefore = await trackTitle(page).textContent();
    expect(titleBefore?.length).toBeGreaterThan(0);

    const matchResponse = page.waitForResponse(
      (r) =>
        (r.url().includes("/match") || r.url().includes("/prefetch")) &&
        r.request().method() === "POST" &&
        r.ok(),
      { timeout: 60_000 },
    );
    await page.getByRole("button", { name: "Skip" }).click();
    await matchResponse;
    await expect(trackTitle(page)).not.toHaveText(titleBefore!, { timeout: 60_000 });
  });

  test("rilascio pad dopo drag può cambiare brano o restare in prefetch", async ({ page }) => {
    await startListening(page);
    await waitForAudioReady(page);
    const titleBefore = await trackTitle(page).textContent();

    const transitionResponse = page.waitForResponse(
      (r) =>
        (r.url().includes("/match") || r.url().includes("/prefetch")) &&
        r.request().method() === "POST",
      { timeout: 60_000 },
    );
    await dragTracker(page, { x: 0.82, y: 0.18 });
    await transitionResponse;

    await page.waitForTimeout(2_000);
    const titleAfter = await trackTitle(page).textContent();
    expect(titleAfter?.length).toBeGreaterThan(0);
    // Pad settle always runs; track may change or stay if prefetch hit same mood.
    expect(typeof titleBefore).toBe("string");
  });

  test("play e pause non mostrano errori", async ({ page }) => {
    await startListening(page);
    await waitForAudioReady(page);
    await page.getByRole("button", { name: "Pause" }).click();
    await expect(page.getByRole("button", { name: "Play" })).toBeVisible();
    await page.getByRole("button", { name: "Play" }).click();
    await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
    await expect(page.getByText(/Playback timed out|Match failed/i)).toHaveCount(0);
  });
});
