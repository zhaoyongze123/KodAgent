#!/usr/bin/env bash
set -euo pipefail

# Deployment smoke check: process-compose must leave exactly one Java OA
# backend for this workspace.  The matcher is intentionally the exact jar
# command used by process-compose, so unrelated Java services are ignored.
app_pids=()
while IFS= read -r pid; do
  [[ -n "$pid" ]] && app_pids+=("$pid")
done < <(
  ps -axo pid=,command= \
    | awk '$2 ~ /\/java$/ && $3 == "-jar" && $4 == "yudao-server/target/yudao-server.jar" {print $1}'
)

if [[ "${#app_pids[@]}" -ne 1 ]]; then
  printf 'expected exactly one yudao-server.jar process, found %s: %s\n' \
    "${#app_pids[@]}" "${app_pids[*]:-<none>}" >&2
  exit 1
fi

listener_pid="$(lsof -tiTCP:48080 -sTCP:LISTEN | head -1 || true)"
if [[ "$listener_pid" != "${app_pids[0]}" ]]; then
  printf 'port 48080 listener (%s) does not match Java process (%s)\n' \
    "${listener_pid:-<none>}" "${app_pids[0]}" >&2
  exit 1
fi

printf 'single Java backend verified: pid=%s listener=%s\n' "${app_pids[0]}" "$listener_pid"
