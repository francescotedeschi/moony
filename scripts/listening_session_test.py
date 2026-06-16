#!/usr/bin/env python3
"""
Simulate ~1h Moony listening via API: match, prefetch, handoffs, skips.
Logs anomalies to stdout and optional log file.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

DEFAULT_API = "http://127.0.0.1:8090"
JOY = {"v": 0.8, "ar": 0.6}
PAD_MOODS = [
    {"v": 0.0, "ar": -0.8, "name": "calm"},
    {"v": 0.8, "ar": 0.6, "name": "joy"},
    {"v": 0.2, "ar": 0.9, "name": "energy"},
    {"v": -0.5, "ar": 0.7, "name": "tension"},
    {"v": -0.7, "ar": -0.5, "name": "sad"},
]
SLOW_MS = 5000


@dataclass
class SessionLog:
    issues: list[str] = field(default_factory=list)
    tracks_played: list[str] = field(default_factory=list)
    transitions: int = 0
    api_errors: int = 0
    match_404: int = 0
    duplicate_in_session: int = 0

    def issue(self, code: str, msg: str) -> None:
        line = f"[{code}] {msg}"
        self.issues.append(line)
        print(line, flush=True)


class ApiClient:
    def __init__(self, base: str, log: SessionLog) -> None:
        self.base = base.rstrip("/")
        self.log = log

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        timeout: float = 120.0,
    ) -> tuple[int, Any, float]:
        url = f"{self.base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method=method,
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                raw = resp.read()
                parsed = json.loads(raw) if raw else None
                if elapsed_ms > SLOW_MS:
                    self.log.issue(
                        "SLOW",
                        f"{method} {path} took {elapsed_ms:.0f}ms",
                    )
                return resp.status, parsed, elapsed_ms
        except urllib.error.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self.log.api_errors += 1
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            self.log.issue("HTTP", f"{method} {path} → {exc.code}: {detail}")
            return exc.code, None, elapsed_ms
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            self.log.api_errors += 1
            self.log.issue("NET", f"{method} {path} → {exc!r}")
            return 0, None, elapsed_ms

    def health(self) -> dict | None:
        _, data, _ = self._request("GET", "/health")
        return data if isinstance(data, dict) else None

    def match(self, payload: dict) -> dict | None:
        code, data, _ = self._request("POST", "/match", payload)
        if code == 404:
            self.log.match_404 += 1
            self.log.issue("MATCH_EMPTY", json.dumps(payload.get("position")))
        return data if code == 200 and isinstance(data, dict) else None

    def prefetch(self, payload: dict) -> dict | None:
        _, data, _ = self._request("POST", "/prefetch", payload)
        return data if isinstance(data, dict) else None

    def timeline(self, track_id: str) -> dict | None:
        _, data, _ = self._request("GET", f"/tracks/{track_id}/timeline")
        return data if isinstance(data, dict) else None

    def record_play(self, track_id: str) -> None:
        self._request("POST", f"/tracks/{track_id}/played")


def pick_prefetch_candidate(
    intents: dict[str, list], played: set[str], *, same_mood: bool = False
) -> dict | None:
    key = "0" if same_mood else None
    if same_mood:
        pool = intents.get("0") or []
    else:
        pool = []
        for k, lst in intents.items():
            if k == "0":
                continue
            pool.extend(lst or [])
    for c in pool:
        tid = c.get("track_id")
        if tid and tid not in played:
            return c
    return None


def simulate_listen_sec(timeline: dict | None, fallback: float = 150.0) -> float:
    if not timeline:
        return fallback + random.uniform(-20, 40)
    dur_ms = timeline.get("duration_ms") or 0
    if dur_ms <= 0 and timeline.get("segments"):
        dur_ms = max(s["t_end"] for s in timeline["segments"])
    dur_sec = max(60.0, dur_ms / 1000.0) if dur_ms else fallback
    # Simulate partial listen until handoff zone (~last 20% or min 90s)
    listen = min(dur_sec * random.uniform(0.55, 0.88), dur_sec - 30)
    return max(45.0, listen)


def run_session(api: ApiClient, log: SessionLog, duration_sec: float, seed: int) -> None:
    rng = random.Random(seed)
    played: set[str] = set()
    t_end = time.monotonic() + duration_sec
    track: dict | None = None
    t_ms = 0
    bpm = 120
    position = dict(JOY)

    health = api.health()
    if not health:
        log.issue("FATAL", "health check failed")
        return
    ps = health.get("play_stats") or {}
    if not ps.get("enabled"):
        log.issue("PLAY_STATS", "global play stats disabled — counts/fairness inactive")
    print(
        f"Session start catalog={health.get('catalog', {}).get('track_count')} "
        f"play_stats={ps} duration={duration_sec}s seed={seed}",
        flush=True,
    )

    # Session seed
    track = api.match(
        {
            "position": JOY,
            "direction": {"v": 0, "ar": 0},
            "bpm_current": 120,
            "exclude_ids": [],
            "pad_only": True,
            "session_seed": True,
        }
    )
    if not track:
        log.issue("FATAL", "session_seed match failed")
        return

    tid = track["track_id"]
    played.add(tid)
    log.tracks_played.append(tid)
    api.record_play(tid)
    bpm = track.get("bpm") or 120
    t_ms = track.get("start_ms") or 0
    timeline = api.timeline(tid)

    while time.monotonic() < t_end:
        listen_sec = simulate_listen_sec(timeline)
        remaining = t_end - time.monotonic()
        if listen_sec > remaining:
            listen_sec = max(0, remaining - 5)
        if listen_sec <= 0:
            break

        print(
            f"  ▶ {track['title'][:40]} ({tid}) listen ~{listen_sec:.0f}s t_ms≈{t_ms}",
            flush=True,
        )
        time.sleep(listen_sec)
        t_ms += int(listen_sec * 1000)

        if time.monotonic() >= t_end:
            break

        # Penultimate same-mood prefetch
        api.prefetch(
            {
                "current_track_id": tid,
                "t_ms": t_ms,
                "position": position,
                "bpm_current": bpm,
                "exclude_ids": list(played),
                "same_mood_only": True,
                "depth": 1,
            }
        )

        roll = rng.random()
        same_mood = roll < 0.55
        action = "same_mood" if same_mood else ("skip" if roll < 0.85 else "pad")

        if action == "pad":
            mood = rng.choice(PAD_MOODS)
            position = {"v": mood["v"], "ar": mood["ar"]}
            print(f"  ↪ pad → {mood['name']}", flush=True)

        prefetch = api.prefetch(
            {
                "current_track_id": tid,
                "t_ms": t_ms,
                "position": position,
                "bpm_current": bpm,
                "exclude_ids": list(played),
                "depth": 1,
            }
        )
        intents = (prefetch or {}).get("intents") or {}
        if not any(intents.get(k) for k in intents):
            log.issue("PREFETCH_EMPTY", f"no candidates at t_ms={t_ms} track={tid}")

        candidate = pick_prefetch_candidate(intents, played, same_mood=same_mood)
        next_track: dict | None = None

        if candidate:
            next_track = {
                "track_id": candidate["track_id"],
                "title": candidate.get("title", ""),
                "bpm": candidate.get("bpm", bpm),
                "start_ms": candidate.get("audio_start_ms", 0),
                "segment": candidate.get("segment", {}),
                "crossfade_ms": candidate.get("crossfade_ms"),
            }
        else:
            payload = {
                "position": position,
                "direction": {"v": 0, "ar": 0},
                "bpm_current": bpm,
                "exclude_ids": list(played),
                "current_track_id": tid,
                "current_t_ms": t_ms,
                "pad_only": not same_mood,
                "same_mood_handoff": same_mood,
            }
            if action == "skip" or not same_mood:
                payload["current_track_id"] = None
                payload["current_t_ms"] = None
            next_track = api.match(payload)

        if not next_track:
            log.issue("STALL", f"no next track after {action} from {tid}")
            # Try broad match
            next_track = api.match(
                {
                    "position": position,
                    "direction": {"v": 0, "ar": 0},
                    "bpm_current": bpm,
                    "exclude_ids": list(played),
                    "pad_only": True,
                }
            )
            if not next_track:
                log.issue("FATAL", "catalog exhausted or repeated failures")
                break

        new_tid = next_track["track_id"]
        if new_tid in played:
            log.duplicate_in_session += 1
            log.issue(
                "DUPLICATE",
                f"track {new_tid} replayed in session (exclude broken?) action={action}",
            )
        if not next_track.get("crossfade_ms") and action != "pad":
            log.issue("CROSSFADE", f"missing crossfade_ms for {new_tid}")

        played.add(new_tid)
        log.tracks_played.append(new_tid)
        log.transitions += 1
        api.record_play(new_tid)

        track = next_track
        tid = new_tid
        bpm = track.get("bpm") or bpm
        t_ms = track.get("start_ms") or 0
        timeline = api.timeline(tid)
        print(
            f"  → {action} → {track.get('title', tid)[:40]} ({tid})",
            flush=True,
        )

    # Summary
    print("\n=== SESSION SUMMARY ===", flush=True)
    print(f"Duration target: {duration_sec}s", flush=True)
    print(f"Tracks played: {len(log.tracks_played)} unique={len(set(log.tracks_played))}", flush=True)
    print(f"Transitions: {log.transitions}", flush=True)
    print(f"API errors: {log.api_errors} match_404: {log.match_404}", flush=True)
    print(f"Duplicates in session: {log.duplicate_in_session}", flush=True)
    print(f"Issues logged: {len(log.issues)}", flush=True)
    if log.issues:
        print("\n--- All issues ---", flush=True)
        for line in log.issues:
            print(line, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Moony API listening session test")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--duration-sec", type=float, default=3600.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--log-file", default="")
    args = parser.parse_args()

    log = SessionLog()
    api = ApiClient(args.api, log)

    if args.log_file:
        import contextlib

        class Tee:
            def __init__(self, *files):
                self.files = files

            def write(self, data):
                for f in self.files:
                    f.write(data)

            def flush(self):
                for f in self.files:
                    f.flush()

        f = open(args.log_file, "w", encoding="utf-8")
        with contextlib.redirect_stdout(Tee(sys.stdout, f)):
            run_session(api, log, args.duration_sec, args.seed)
        f.close()
    else:
        run_session(api, log, args.duration_sec, args.seed)

    return 1 if log.api_errors or log.duplicate_in_session or log.match_404 > 3 else 0


if __name__ == "__main__":
    raise SystemExit(main())
