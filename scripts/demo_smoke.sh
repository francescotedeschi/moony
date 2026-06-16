#!/usr/bin/env bash
# Quick smoke test for Moony demo (API must be up on :8090).
set -euo pipefail
API="${API:-http://127.0.0.1:8090}"

echo "Health…"
curl -sf "$API/health" | python3 -m json.tool

echo ""
echo "Match Calm → Sad-like target…"
curl -sf "$API/match" \
  -H 'Content-Type: application/json' \
  -d '{"position":{"v":-0.7,"ar":-0.5},"direction":{"v":-0.1,"ar":0},"bpm_current":110,"exclude_ids":[]}' \
  | python3 -m json.tool | head -30

echo ""
echo "Match Joy…"
curl -sf "$API/match" \
  -H 'Content-Type: application/json' \
  -d '{"position":{"v":0.8,"ar":0.6},"direction":{"v":0, "ar":0},"bpm_current":110,"exclude_ids":[]}' \
  | python3 -m json.tool | head -30

echo "OK"
