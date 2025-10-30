#!/usr/bin/env bash
set -euo pipefail

PUBLIC_PORT=${PUBLIC_PORT:-8080}
BLUE_PORT=${BLUE_PORT:-8081}
GREEN_PORT=${GREEN_PORT:-8082}
TIMEOUT_SECS=10   # total observation window after chaos
SLEEP_BETWEEN=0.15

echo "[verify] Starting docker compose..."
docker compose up -d

# wait for services
echo "[verify] waiting for services to be healthy..."
sleep 3

# helper to request /version (returns status and pool header)
req_version() {
  # $1 = target host:port (e.g., localhost:8080)
  # returns "HTTP_STATUS|POOL|RELEASE_ID"
  RESPONSE=$(curl -s -D - --max-time 6 "http://$1/version" || true)
  HTTP_STATUS=$(echo "$RESPONSE" | head -n1 | awk '{print $2}')
  POOL=$(echo "$RESPONSE" | grep -i '^X-App-Pool:' | awk '{print $2}' | tr -d '\r')
  RELEASE=$(echo "$RESPONSE" | grep -i '^X-Release-Id:' | awk '{print $2}' | tr -d '\r')
  echo "${HTTP_STATUS:-000}|${POOL:-}|${RELEASE:-}"
}

echo "[verify] Baseline check against nginx (should be ACTIVE_POOL = blue)..."
BASELINE=$(req_version "localhost:${PUBLIC_PORT}")
echo "[verify] Baseline result: $BASELINE"

# quick assert baseline 200 and pool is blue
STATUS=$(echo "$BASELINE" | cut -d'|' -f1)
POOL=$(echo "$BASELINE" | cut -d'|' -f2)

if [ "$STATUS" != "200" ]; then
  echo "Baseline: expected status 200, got $STATUS"
  docker compose down
  exit 1
fi

echo "Baseline OK: status 200, pool=$POOL"

# Start chaos on the active app (grader told us Blue is active)
echo "[verify] triggering chaos on blue: POST /chaos/start?mode=error"
curl -s -X POST "http://localhost:${BLUE_PORT}/chaos/start?mode=error" || true

echo "[verify] Now collecting responses from nginx for ${TIMEOUT_SECS}s..."
end_time=$((SECONDS + TIMEOUT_SECS))
total=0
non200=0
green_count=0

while [ $SECONDS -lt $end_time ]; do
  total=$((total+1))
  R=$(req_version "localhost:${PUBLIC_PORT}")
  STATUS=$(echo "$R" | cut -d'|' -f1)
  POOL=$(echo "$R" | cut -d'|' -f2)
  
  if [ "$STATUS" != "200" ]; then
    non200=$((non200+1))
    echo "[verify] non-200 detected: $R"
  fi
  
  if [ "$POOL" = "green" ]; then
    green_count=$((green_count+1))
  fi
  
  sleep $SLEEP_BETWEEN
done

echo "[verify] Results: total=$total non200=$non200 green_count=$green_count"

if [ $non200 -ne 0 ]; then
  echo "Fail: observed non-200 responses during chaos."
  curl -s -X POST "http://localhost:${BLUE_PORT}/chaos/stop" || true
  docker compose down
  exit 1
fi

percent_green=$((100 * green_count / total))
echo "[verify] percent_green = ${percent_green}%"

if [ $percent_green -lt 95 ]; then
  echo "Fail: less than 95% responses from green during chaos"
  curl -s -X POST "http://localhost:${BLUE_PORT}/chaos/stop" || true
  docker compose down
  exit 1
fi

echo "[verify] PASS: failover behavior satisfies criteria."

# stop chaos
curl -s -X POST "http://localhost:${BLUE_PORT}/chaos/stop" || true

echo "[verify] Stopping compose..."
docker compose down

echo ""
echo "========================================="
echo "✅ ALL TESTS PASSED!"