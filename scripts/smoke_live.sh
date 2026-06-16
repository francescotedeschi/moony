#!/usr/bin/env bash
# Live smoke against running Moony stack (default API :8090).
set -euo pipefail

API="${MOONY_API:-http://localhost:8090}"
FAIL=0

check() {
  local name="$1"
  shift
  if "$@"; then
    echo "OK  $name"
  else
    echo "FAIL $name"
    FAIL=1
  fi
}

echo "=== Moony live smoke → $API ==="

check "health" curl -sf "$API/health" -o /tmp/moony_health.json
python3 - <<'PY'
import json, sys
h = json.load(open("/tmp/moony_health.json"))
assert h["status"] == "ok", h
assert h["catalog"]["track_count"] > 0
ps = h["play_stats"]
assert ps["enabled"] is True, f"play_stats disabled: {ps}"
print(f"  catalog tracks={h['catalog']['track_count']} play_stats enabled total_plays={ps['total_plays']}")
PY

MATCH_JSON=$(curl -sf -X POST "$API/match" -H 'Content-Type: application/json' -d '{
  "position": {"v": 0.2, "ar": -0.3},
  "direction": {"v": 0, "ar": 0},
  "bpm_current": 120,
  "exclude_ids": [],
  "pad_only": true
}')
TID=$(echo "$MATCH_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['track_id'])")
echo "  match track_id=$TID"

PLAY_JSON=$(curl -sf "$API/tracks/$TID/play-count")
echo "$PLAY_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['stats_enabled'] and d['track_id'], d
"
echo "OK  play-count GET"

BEFORE=$(curl -sf "$API/tracks/$TID/play-count" | python3 -c "import sys,json; print(json.load(sys.stdin)['play_count'])")
AFTER=$(curl -sf -X POST "$API/tracks/$TID/played" | python3 -c "import sys,json; print(json.load(sys.stdin)['play_count'])")
if [ "$AFTER" -eq $((BEFORE + 1)) ]; then
  echo "OK  play increment $BEFORE → $AFTER"
else
  echo "FAIL play increment expected $((BEFORE+1)) got $AFTER"
  FAIL=1
fi

curl -sf -X POST "$API/prefetch" -H 'Content-Type: application/json' -d "{
  \"position\": {\"v\": 0.2, \"ar\": -0.3},
  \"direction\": {\"v\": 0, \"ar\": 0},
  \"bpm_current\": 120,
  \"current_track_id\": \"$TID\",
  \"current_t_ms\": 5000,
  \"exclude_ids\": [\"$TID\"]
}" -o /tmp/moony_prefetch.json
if python3 -c "
import json
d = json.load(open('/tmp/moony_prefetch.json'))
assert 'intents' in d and len(d['intents']) > 0
"; then
  echo "OK  prefetch"
else
  echo "FAIL prefetch"
  FAIL=1
fi

check "exclude_ids respected" python3 - <<PY
import json, urllib.request
payload = {
  "position": {"v": 0.2, "ar": -0.3},
  "direction": {"v": 0, "ar": 0},
  "bpm_current": 120,
  "exclude_ids": ["$TID"],
  "pad_only": True,
}
req = urllib.request.Request(
    "$API/match",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as r:
    m = json.load(r)
assert m["track_id"] != "$TID", m
PY

if curl -sf -r 0-2048 "$API/tracks/$TID/audio" -o /dev/null; then
  echo "OK  audio stream (track proxy)"
else
  echo "FAIL audio stream (track proxy)"
  FAIL=1
fi

if [ "$FAIL" -eq 0 ]; then
  echo "=== All live checks passed ==="
else
  echo "=== Some checks failed ==="
  exit 1
fi
