import { api } from "./api";
import { buildCatalogMoodSlices, type CatalogMoodSlice } from "./catalogMoodSlices";

let cachedSlices: CatalogMoodSlice[] | null = null;
let loadPromise: Promise<CatalogMoodSlice[]> | null = null;

export function getCatalogMoodArcSlices(): CatalogMoodSlice[] | null {
  return cachedSlices;
}

export function setCatalogMoodArcSlices(
  labels: readonly string[],
  shares: readonly number[],
): CatalogMoodSlice[] {
  cachedSlices = buildCatalogMoodSlices(labels, shares);
  return cachedSlices;
}

export function loadCatalogMoodArcSlices(signal?: AbortSignal): Promise<CatalogMoodSlice[]> {
  if (cachedSlices) return Promise.resolve(cachedSlices);
  if (!loadPromise) {
    loadPromise = api
      .catalogStats(signal)
      .then((stats) => setCatalogMoodArcSlices(stats.mood_labels, stats.mood_segment_share))
      .catch((err) => {
        loadPromise = null;
        throw err;
      });
  }
  return loadPromise;
}
