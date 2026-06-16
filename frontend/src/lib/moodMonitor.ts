/**
 * Session mood diagnostics — pad target mood and highlighted user actions.
 * Enable: dev build or `?mood=1` (also `?monitor=1` for backwards compatibility).
 *
 * Session time advances only while playback is active (pauses with the player).
 */

import { EMOTION_ZONES, moodColorForName, nearestEmotionZone } from "./emotions";

export type MoodSessionStats = {
  moodShare: { zone: string; share: number }[];
  tracksPlayed: number;
  skipCount: number;
};

export type MoodUserAction =
  | "session_start"
  | "mood_select"
  | "mood_change"
  | "same_mood_change"
  | "skip"
  | "replay"
  | "timeline"
  | "next_track";

export type MoodMonitorEvent = {
  id: number;
  /** Elapsed playing ms since session start. */
  at: number;
  kind: MoodUserAction;
  mood: string;
  message: string;
  fromMood?: string;
  toMood?: string;
  detail?: Record<string, unknown>;
};

export type MoodSegment = {
  zone: string;
  /** Elapsed playing ms when this mood segment started. */
  from: number;
  /** Elapsed playing ms when it ended, or null while current. */
  to: number | null;
};

export type MoodTrackEntry = {
  trackId: string;
  title: string;
  artist: string;
  /** Catalog / dominant mood label for display (e.g. Calm, Joy). */
  primaryMood: string;
  /** Global play count from server; null until loaded or stats disabled. */
  playCount: number | null;
  /** Catalog entry point (ms) when this track started. */
  entryMs: number;
  /** Session elapsed ms when this track started. */
  fromMs: number;
  /** Session elapsed ms when replaced; null while current. */
  toMs: number | null;
};

const MAX_EVENTS = 150;

function isMoodMonitorEnabled(): boolean {
  if (import.meta.env.DEV) return true;
  try {
    const params = new URLSearchParams(window.location.search);
    return params.has("mood") || params.has("monitor");
  } catch {
    return false;
  }
}

function zoneAt(v: number, ar: number): string {
  return nearestEmotionZone(v, ar).name;
}

class MoodMonitor {
  private enabled = isMoodMonitorEnabled();
  private events: MoodMonitorEvent[] = [];
  private nextId = 1;
  private listeners = new Set<() => void>();
  private currentZone: string | null = null;
  private sessionActive = false;
  private moodTrail: MoodSegment[] = [];
  private playingMs = 0;
  private resumeWallAt: number | null = null;
  private playbackActive = false;
  private playedTrackIds = new Set<string>();
  private skipCount = 0;
  private trackHistory: MoodTrackEntry[] = [];

  isEnabled(): boolean {
    return this.enabled;
  }

  isPlaybackActive(): boolean {
    return this.playbackActive;
  }

  isSessionActive(): boolean {
    return this.sessionActive;
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  getEvents(): readonly MoodMonitorEvent[] {
    return this.events;
  }

  getCurrentMood(): string | null {
    return this.currentZone;
  }

  getMoodTrail(): readonly MoodSegment[] {
    return this.moodTrail;
  }

  getTrackHistory(): readonly MoodTrackEntry[] {
    return this.trackHistory;
  }

  /** Elapsed playing time in ms (frozen while paused). */
  getElapsedMs(): number {
    if (!this.sessionActive) return 0;
    if (this.resumeWallAt != null) {
      return this.playingMs + (Date.now() - this.resumeWallAt);
    }
    return this.playingMs;
  }

  getSessionStats(): MoodSessionStats {
    const elapsed = Math.max(this.getElapsedMs(), 1);
    const byZone = new Map<string, number>();
    for (const seg of this.moodTrail) {
      const end = seg.to ?? this.getElapsedMs();
      byZone.set(seg.zone, (byZone.get(seg.zone) ?? 0) + Math.max(0, end - seg.from));
    }
    return {
      moodShare: EMOTION_ZONES.map((z) => ({
        zone: z.name,
        share: (byZone.get(z.name) ?? 0) / elapsed,
      })),
      tracksPlayed: this.playedTrackIds.size,
      skipCount: this.skipCount,
    };
  }

  private notify() {
    this.listeners.forEach((l) => l());
  }

  private sessionClock(): number {
    return this.getElapsedMs();
  }

  setPlaybackActive(active: boolean) {
    if (!this.enabled || !this.sessionActive) return;
    const now = Date.now();

    if (active && !this.playbackActive) {
      this.resumeWallAt = now;
    } else if (!active && this.playbackActive) {
      if (this.resumeWallAt != null) {
        this.playingMs += now - this.resumeWallAt;
        this.resumeWallAt = null;
      }
    }

    this.playbackActive = active;
    this.notify();
  }

  private emit(
    kind: MoodUserAction,
    mood: string,
    message: string,
    extra?: { fromMood?: string; toMood?: string; detail?: Record<string, unknown> },
  ) {
    if (!this.enabled) return;
    const ev: MoodMonitorEvent = {
      id: this.nextId++,
      at: this.sessionClock(),
      kind,
      mood,
      message,
      fromMood: extra?.fromMood,
      toMood: extra?.toMood,
      detail: extra?.detail,
    };
    this.events = [...this.events.slice(-(MAX_EVENTS - 1)), ev];
    console.log(`[moony-mood] ${message}`, extra?.detail ?? "");
    this.notify();
  }

  private advanceZone(zone: string) {
    if (this.currentZone === zone) return;
    const prev = this.currentZone;
    this.currentZone = zone;

    if (this.sessionActive) {
      const t = this.sessionClock();
      const last = this.moodTrail[this.moodTrail.length - 1];
      if (last && last.to === null) last.to = t;
      this.moodTrail.push({ zone, from: t, to: null });
    }

    if (prev && this.sessionActive) {
      this.emit("mood_select", zone, `${prev} → ${zone}`, { fromMood: prev, toMood: zone });
    } else {
      this.notify();
    }
  }

  sessionStart(v: number, ar: number) {
    if (!this.enabled) return;
    this.sessionActive = true;
    this.playingMs = 0;
    this.resumeWallAt = null;
    this.playbackActive = false;
    this.events = [];
    this.moodTrail = [];
    this.playedTrackIds = new Set();
    this.skipCount = 0;
    this.trackHistory = [];
    const zone = zoneAt(v, ar);
    this.currentZone = zone;
    this.moodTrail.push({ zone, from: 0, to: null });
    this.emit("session_start", zone, `Session started · ${zone}`, { detail: { v, ar } });
  }

  sessionEnd() {
    if (!this.enabled || !this.sessionActive) return;
    const last = this.moodTrail[this.moodTrail.length - 1];
    if (last && last.to === null) last.to = this.sessionClock();
    const lastTrack = this.trackHistory[this.trackHistory.length - 1];
    if (lastTrack && lastTrack.toMs === null) {
      lastTrack.toMs = this.sessionClock();
    }
    this.sessionActive = false;
    this.playbackActive = false;
    this.resumeWallAt = null;
    this.notify();
  }

  onPadPosition(v: number, ar: number) {
    if (!this.enabled || !this.sessionActive) return;
    this.advanceZone(zoneAt(v, ar));
  }

  trackPlayed(trackId: string) {
    if (!this.enabled || !this.sessionActive) return;
    if (this.playedTrackIds.has(trackId)) return;
    this.playedTrackIds.add(trackId);
    this.notify();
  }

  trackStarted(entry: {
    trackId: string;
    title: string;
    artist: string;
    primaryMood: string;
    entryMs?: number;
    playCount?: number | null;
    atMs?: number;
  }) {
    if (!this.enabled || !this.sessionActive) return;
    const at = entry.atMs ?? this.sessionClock();
    const last = this.trackHistory[this.trackHistory.length - 1];
    if (last && last.toMs === null) {
      last.toMs = at;
    }
    this.trackHistory.push({
      trackId: entry.trackId,
      title: entry.title,
      artist: entry.artist,
      primaryMood: entry.primaryMood,
      playCount: entry.playCount ?? null,
      entryMs: entry.entryMs ?? 0,
      fromMs: at,
      toMs: null,
    });
    this.playedTrackIds.add(entry.trackId);
    this.notify();
  }

  updateTrackPlayCount(trackId: string, playCount: number | null) {
    if (!this.enabled) return;
    for (let i = this.trackHistory.length - 1; i >= 0; i--) {
      if (this.trackHistory[i].trackId === trackId) {
        this.trackHistory[i].playCount = playCount;
        this.notify();
        return;
      }
    }
  }

  userAction(
    action: Exclude<MoodUserAction, "session_start" | "mood_select">,
    opts: { v: number; ar: number; fromZone?: string; detail?: Record<string, unknown> },
  ) {
    if (!this.enabled || !this.sessionActive) return;
    const mood = zoneAt(opts.v, opts.ar);
    this.advanceZone(mood);

    switch (action) {
      case "mood_change": {
        const from = opts.fromZone ?? "?";
        this.emit("mood_change", mood, `Mood change · ${from} → ${mood}`, {
          fromMood: from,
          toMood: mood,
          detail: { v: opts.v, ar: opts.ar, ...opts.detail },
        });
        break;
      }
      case "same_mood_change":
        this.emit(
          "same_mood_change",
          mood,
          `New track · same mood (${mood})`,
          { detail: { v: opts.v, ar: opts.ar, ...opts.detail } },
        );
        break;
      case "skip":
        this.skipCount += 1;
        this.emit("skip", mood, `Skip · ${mood}`, {
          detail: { v: opts.v, ar: opts.ar, ...opts.detail },
        });
        break;
      case "replay":
        this.emit("replay", mood, `Replay · ${mood}`, {
          detail: { v: opts.v, ar: opts.ar, ...opts.detail },
        });
        break;
      case "timeline":
        this.emit("timeline", mood, `Timeline pick · ${mood}`, {
          detail: { v: opts.v, ar: opts.ar, ...opts.detail },
        });
        break;
      case "next_track":
        this.emit("next_track", mood, `Next track · ${mood}`, {
          detail: { v: opts.v, ar: opts.ar, ...opts.detail },
        });
        break;
    }
  }
}

export const moodMonitor = new MoodMonitor();
export { moodColorForName };
