#!/usr/bin/env bash
# Foreground mood monitor session — stack up + instructions.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WEB_PORT="${WEB_HOST_PORT:-5190}"
API_PORT="${API_HOST_PORT:-8090}"
URL="http://localhost:${WEB_PORT}/?mood=1"

echo "==> Starting Moony stack (docker compose)…"
docker compose up -d postgres api web

echo "==> Waiting for API health…"
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo ""
echo "Mood monitor session ready."
echo "  URL: ${URL}"
echo ""
echo "Watch the rose panel bottom-left + browser console [moony-mood]."
echo "Tracks pad mood, skip, mood change, same-mood change, replay."
echo ""

if command -v open >/dev/null 2>&1; then
  open "${URL}"
fi
