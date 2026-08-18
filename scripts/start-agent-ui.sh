#!/usr/bin/env bash

set -u

cd /Users/mac/项目/kodagent/agent-chat-ui

export NODE_OPTIONS="--max-old-space-size=4096${NODE_OPTIONS:+ $NODE_OPTIONS}"

old_pids=$(lsof -ti :3000 2>/dev/null || true)
if [ -n "$old_pids" ]; then
  echo "[agent-ui] stopping stale processes on port 3000..."
  kill $old_pids 2>/dev/null || true
  for _ in $(seq 1 10); do
    if ! lsof -ti :3000 >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  remaining_pids=$(lsof -ti :3000 2>/dev/null || true)
  [ -z "$remaining_pids" ] || kill -9 $remaining_pids 2>/dev/null || true
fi

echo "[agent-ui] starting Next.js development server..."
pnpm exec next dev --port 3000 &
next_pid=$!

cleanup() {
  kill "$next_pid" 2>/dev/null || true
  wait "$next_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Next.js opens its port before the first route has finished compiling.
# Wait for the listener, then compile the SSO route in the background of the
# restart operation instead of making the first user request pay the cost.
for _ in $(seq 1 120); do
  if curl -fsS --max-time 1 http://127.0.0.1:3000/auth/kod-sso >/dev/null 2>&1; then
    echo "[agent-ui] SSO route prewarmed."
    # The successful SSO flow immediately redirects to the chat home page.
    # Warm it as well so the redirect does not trigger another cold compile.
    curl -fsS --max-time 600 http://127.0.0.1:3000/ >/dev/null 2>&1 &
    # Warm routes used by the first historical-thread and settings visits.
    # These requests intentionally run without a browser cookie; they compile
    # the Next routes and return quickly with the expected auth response.
    curl -fsS --max-time 600 http://127.0.0.1:3000/settings >/dev/null 2>&1 &
    curl -fsS --max-time 600 http://127.0.0.1:3000/api/auth/kod-sso/session >/dev/null 2>&1 &
    curl -fsS --max-time 600 http://127.0.0.1:3000/api/agent-settings/providers >/dev/null 2>&1 &
    curl -fsS --max-time 600 http://127.0.0.1:3000/api/agent-events/prewarm >/dev/null 2>&1 &
    curl -fsS --max-time 600 http://127.0.0.1:3000/api/agent-state/prewarm >/dev/null 2>&1 &
    break
  fi

  if ! kill -0 "$next_pid" 2>/dev/null; then
    wait "$next_pid"
    exit $?
  fi
  sleep 1
done

wait "$next_pid"
